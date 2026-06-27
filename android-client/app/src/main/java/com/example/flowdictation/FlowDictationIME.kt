package com.example.flowdictation

import android.Manifest
import android.animation.ObjectAnimator
import android.animation.PropertyValuesHolder
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.inputmethodservice.InputMethodService
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.ExtractedTextRequest
import android.widget.LinearLayout
import android.widget.RelativeLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import com.google.ai.client.generativeai.GenerativeModel
import com.google.ai.client.generativeai.type.content
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.delay
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import org.json.JSONArray
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import android.graphics.BitmapFactory
import android.content.BroadcastReceiver
import android.content.IntentFilter
import android.provider.MediaStore
import java.io.File
import com.google.firebase.firestore.FirebaseFirestore

class FlowDictationIME : InputMethodService() {
    private lateinit var mainContainer: LinearLayout
    private lateinit var qwertyContainer: LinearLayout
    private lateinit var symbolContainer: LinearLayout
    private lateinit var deepSymbolContainer: LinearLayout
    private lateinit var calcContainer: LinearLayout
    private lateinit var spacebarButton: RelativeLayout
    private lateinit var dictationButton: TextView
    private lateinit var calcDisplay: TextView
    
    private var isRecording = false
    private var isOmniMode = false
    private var isShifted = false
    private var currentCalcText = ""
    private var spacebarAnimator: ObjectAnimator? = null
    private var recordingAnimator: ObjectAnimator? = null

    private var audioRecord: AudioRecord? = null
    private var recordingThread: Thread? = null
    private val sampleRate = 16000
    private val bufferSize = AudioRecord.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
    private val audioBuffer = ByteArrayOutputStream()

    private val serviceJob = Job()
    private val coroutineScope = CoroutineScope(Dispatchers.Main + serviceJob)

    private val groqApiKey = "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"
    private val geminiApiKey = "AQ.Ab8RN6KTliPSGU-JoFsYSY1MayugE5NFp2MVpNNvQLJg9YiT8w"
    
    private val keyViews = mutableListOf<TextView>()

    private val db by lazy { FirebaseFirestore.getInstance() }
    private var globalDictionary = ""
    private var omniCommands = mutableMapOf<String, String>()

    private val cameraResultReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val pathStr = intent?.getStringExtra("image_path")
            if (pathStr != null) scanPlacardWithGemini(pathStr)
        }
    }

    override fun onCreate() {
        super.onCreate()
        val filter = IntentFilter("com.example.flowdictation.CAMERA_RESULT")
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(cameraResultReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(cameraResultReceiver, filter)
        }
    }

    override fun onCreateInputView(): View {
        val density = resources.displayMetrics.density

        db.collection("dictionary").get().addOnSuccessListener { result ->
            val entries = mutableListOf<String>()
            for (document in result) {
                val word = document.getString("word")
                val replacement = document.getString("replacement")
                if (word != null && replacement != null) entries.add("$word -> $replacement")
            }
            if (entries.isNotEmpty()) globalDictionary = "Custom Dictionary: \n" + entries.joinToString("\n")
        }
        
        db.collection("omni_commands").addSnapshotListener { snapshot, e ->
            if (e != null) return@addSnapshotListener
            omniCommands.clear()
            for (doc in snapshot!!) {
                val trigger = doc.getString("trigger")?.lowercase()
                val action = doc.getString("action")
                if (trigger != null && action != null) omniCommands[trigger] = action
            }
        }
        
        mainContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            setBackgroundColor(Color.parseColor("#121212"))
            setPadding(0, (5 * density).toInt(), 0, 0)
        }

        val toolbarContainer = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            setPadding((2 * density).toInt(), (2 * density).toInt(), (2 * density).toInt(), (5 * density).toInt())
            weightSum = 5f
        }

        dictationButton = createToolbarButton("🎤 Flow", "#2A2A2A", "#FFFFFF", weight = 1f) {
            if (ContextCompat.checkSelfPermission(this@FlowDictationIME, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) toggleDictation()
        }
        dictationButton.layoutParams = LinearLayout.LayoutParams(0, (80 * density).toInt(), 1f).apply {
            setMargins((1 * density).toInt(), (1 * density).toInt(), (1 * density).toInt(), (1 * density).toInt())
        }
        toolbarContainer.addView(dictationButton)

        val rightContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 4f)
        }

        val toolbarRow1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 4f }
        val toolbarRow2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 4f }
        
        val btnPaste = createToolbarButton("📋 Paste", "#1E1E1E", "#AAAAAA", weight = 1f) {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.primaryClip?.getItemAt(0)?.text?.let { currentInputConnection?.commitText(it, 1) }
        }
        val btnSelectAll = createToolbarButton("🎯 Select", "#1E1E1E", "#FFFF55", weight = 1f) {
            val ic = currentInputConnection
            val text = ic?.getExtractedText(ExtractedTextRequest(), 0)?.text ?: return@createToolbarButton
            ic.setSelection(0, text.length)
        }
        val btnCopy = createToolbarButton("📋 Copy", "#1E1E1E", "#55AAFF", weight = 1f) { currentInputConnection?.performContextMenuAction(android.R.id.copy) }
        val btnNuke = createToolbarButton("💣 Nuke", "#1E1E1E", "#FF5555", weight = 1f) { currentInputConnection?.deleteSurroundingText(10000, 10000) }
        
        toolbarRow1.addView(btnPaste)
        toolbarRow1.addView(btnSelectAll)
        toolbarRow1.addView(btnCopy)
        toolbarRow1.addView(btnNuke)
        
        val btnGemini = createToolbarButton("✦ Gemini", "#1E1E1E", "#AA55FF", weight = 1f) {
            try { 
                val intent = Intent(Intent.ACTION_VOICE_COMMAND)
                intent.setPackage("com.google.android.googlequicksearchbox")
                intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK
                startActivity(intent) 
            } catch (e: Exception) {}
        }
        val btnOmni = createToolbarButton("🪄 Omni", "#1E1E1E", "#55FFAA", weight = 1f) {
            isOmniMode = true
            toggleDictation()
        }
        val btnCalc = createToolbarButton("🧮 Calc", "#1E1E1E", "#FFAA55", weight = 1f) { toggleCalculatorMode() }
        val btnRewrite = createToolbarButton("✨ Fix", "#1E1E1E", "#FF55AA", weight = 1f) { rewriteText() }
        
        toolbarRow2.addView(btnGemini)
        toolbarRow2.addView(btnOmni)
        toolbarRow2.addView(btnCalc)
        toolbarRow2.addView(btnRewrite)

        rightContainer.addView(toolbarRow1)
        rightContainer.addView(toolbarRow2)
        toolbarContainer.addView(rightContainer)
        mainContainer.addView(toolbarContainer)

        qwertyContainer = buildQwertyContainer()
        symbolContainer = buildSymbolContainer()
        deepSymbolContainer = buildDeepSymbolContainer()
        calcContainer = createCalculatorView()
        
        mainContainer.addView(qwertyContainer)
        mainContainer.addView(symbolContainer)
        mainContainer.addView(deepSymbolContainer)
        mainContainer.addView(calcContainer)
        
        val navSpacer = View(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, (50 * density).toInt())
            setBackgroundColor(Color.parseColor("#121212"))
        }
        mainContainer.addView(navSpacer)

        return mainContainer
    }
    
    private fun buildQwertyContainer(): LinearLayout {
        val container = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT) }

        val r0 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        val numbers = listOf("1","2","3","4","5","6","7","8","9","0")
        val subs = listOf("","","","","","","🙂","😛","😂","👎")
        for (i in 0..9) {
            r0.addView(createKeyButton(numbers[i], isSpecial = false, subscript = subs[i], longPressAction = { currentInputConnection?.commitText(if (subs[i].isNotEmpty()) subs[i] else numbers[i], 1) }) {
                currentInputConnection?.commitText(if (isShifted) numbers[i].uppercase() else numbers[i], 1)
                if (isShifted) { isShifted = false; updateShiftState() }
            })
        }
        container.addView(r0)

        val r1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        val qrow = listOf("q","w","e","r","t","y","u","i","o","p")
        for (k in qrow) {
            r1.addView(createKeyButton(k, isSpecial = false, subscript = "") {
                currentInputConnection?.commitText(if (isShifted) k.uppercase() else k, 1)
                if (isShifted) { isShifted = false; updateShiftState() }
            })
        }
        container.addView(r1)

        val r2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        r2.addView(View(this).apply { layoutParams = LinearLayout.LayoutParams(0, 1, 0.5f) })
        val arow = listOf("a","s","d","f","g","h","j","k","l")
        for (k in arow) {
            r2.addView(createKeyButton(k, isSpecial = false, subscript = "") {
                currentInputConnection?.commitText(if (isShifted) k.uppercase() else k, 1)
                if (isShifted) { isShifted = false; updateShiftState() }
            })
        }
        r2.addView(View(this).apply { layoutParams = LinearLayout.LayoutParams(0, 1, 0.5f) })
        container.addView(r2)

        val r3 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        r3.addView(createKeyButton("⇧", isSpecial = true, weight = 1.5f, subscript = "😲", longPressAction = { currentInputConnection?.commitText("😲", 1) }) {
            isShifted = !isShifted; updateShiftState()
        })
        val zrow = listOf("z","x","c","v","b","n","m")
        for (k in zrow) {
            r3.addView(createKeyButton(k, isSpecial = false, subscript = "") {
                currentInputConnection?.commitText(if (isShifted) k.uppercase() else k, 1)
                if (isShifted) { isShifted = false; updateShiftState() }
            })
        }
        r3.addView(createBackspaceButton(1.5f))
        container.addView(r3)

        val bottomRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        bottomRow.addView(createKeyButton("?123", isSpecial = true, weight = 1.5f) { toggleSymbolMode() })
        bottomRow.addView(createKeyButton(",", isSpecial = true, weight = 1f, subscript = "👍", longPressAction = { currentInputConnection?.commitText("👍", 1) }) { currentInputConnection?.commitText(",", 1) })
        bottomRow.addView(createKeyButton("📸", isSpecial = true, weight = 1f) { 
            val intent = Intent(this, CameraCaptureActivity::class.java); intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK); startActivity(intent)
        })
        
        spacebarButton = createSpacebarDictationButton(weight = 4f)
        bottomRow.addView(spacebarButton)
        
        bottomRow.addView(createKeyButton(".", isSpecial = true, weight = 1f, subscript = "🤷‍♂️", longPressAction = { currentInputConnection?.commitText("🤷‍♂️", 1) }) { currentInputConnection?.commitText(".", 1) })
        bottomRow.addView(createKeyButton("↵", isSpecial = true, weight = 1.5f, bgColor = "#4A90E2", textColor = "#FFFFFF") {
            currentInputConnection?.commitText("\n", 1)
        })
        
        container.addView(bottomRow)
        return container
    }

    private fun buildSymbolContainer(): LinearLayout {
        val container = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); visibility = View.GONE }
        val r0 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        val nums = listOf("1","2","3","4","5","6","7","8","9","0")
        for (k in nums) r0.addView(createKeyButton(k, isSpecial = false) { currentInputConnection?.commitText(k, 1) })
        
        val r1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        val syms1 = listOf("@","#","$","_","&","-","+","(",")","/")
        for (k in syms1) r1.addView(createKeyButton(k, isSpecial = false) { currentInputConnection?.commitText(k, 1) })
        
        val r2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        r2.addView(createKeyButton("=\\<", isSpecial = true, weight = 1.5f) { toggleDeepSymbolMode() })
        val syms2 = listOf("*","\"","'",":",";","!","?")
        for (k in syms2) r2.addView(createKeyButton(k, isSpecial = false) { currentInputConnection?.commitText(k, 1) })
        r2.addView(createBackspaceButton(1.5f))
        
        val r3 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        r3.addView(createKeyButton("ABC", isSpecial = true, weight = 1.5f) { toggleSymbolMode() })
        r3.addView(createKeyButton(",", isSpecial = true, weight = 1f, subscript = "👍", longPressAction = { currentInputConnection?.commitText("👍", 1) }) { currentInputConnection?.commitText(",", 1) })
        r3.addView(createKeyButton("📸", isSpecial = true, weight = 1f) { val intent = Intent(this, CameraCaptureActivity::class.java); intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK); startActivity(intent) })
        r3.addView(createKeyButton("Space", isSpecial = false, weight = 4f) { currentInputConnection?.commitText(" ", 1) })
        r3.addView(createKeyButton(".", isSpecial = true, weight = 1f, subscript = "🤷‍♂️", longPressAction = { currentInputConnection?.commitText("🤷‍♂️", 1) }) { currentInputConnection?.commitText(".", 1) })
        r3.addView(createKeyButton("↵", isSpecial = true, weight = 1.5f, bgColor = "#4A90E2", textColor = "#FFFFFF") { currentInputConnection?.commitText("\n", 1) })
        
        container.addView(r0); container.addView(r1); container.addView(r2); container.addView(r3)
        return container
    }

    private fun buildDeepSymbolContainer(): LinearLayout {
        val container = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); visibility = View.GONE }
        val r0 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        val syms1 = listOf("~","`","|","•","√","π","÷","×","§","δ")
        for (k in syms1) r0.addView(createKeyButton(k, isSpecial = false) { currentInputConnection?.commitText(k, 1) })
        
        val r1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        val syms2 = listOf("£","¢","€","¥","^","°","=","{","}","\\")
        for (k in syms2) r1.addView(createKeyButton(k, isSpecial = false) { currentInputConnection?.commitText(k, 1) })
        
        val r2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        r2.addView(createKeyButton("?123", isSpecial = true, weight = 1.5f) { toggleSymbolMode() })
        val syms3 = listOf("%","©","®","™","✓","[","]")
        for (k in syms3) r2.addView(createKeyButton(k, isSpecial = false) { currentInputConnection?.commitText(k, 1) })
        r2.addView(createBackspaceButton(1.5f))
        
        val r3 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        r3.addView(createKeyButton("ABC", isSpecial = true, weight = 1.5f) { toggleSymbolMode() })
        r3.addView(createKeyButton("<", isSpecial = true, weight = 1f) { currentInputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_DPAD_LEFT)); currentInputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_DPAD_LEFT)) })
        r3.addView(createKeyButton("1234", isSpecial = true, weight = 1f) { toggleCalculatorMode() })
        r3.addView(createKeyButton("Space", isSpecial = false, weight = 4f) { currentInputConnection?.commitText(" ", 1) })
        r3.addView(createKeyButton(">", isSpecial = true, weight = 1f) { currentInputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_DPAD_RIGHT)); currentInputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_DPAD_RIGHT)) })
        r3.addView(createKeyButton("↵", isSpecial = true, weight = 1.5f, bgColor = "#4A90E2", textColor = "#FFFFFF") { currentInputConnection?.commitText("\n", 1) })
        
        container.addView(r0); container.addView(r1); container.addView(r2); container.addView(r3)
        return container
    }

    private fun createCalculatorView(): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            visibility = View.GONE
            calcDisplay = TextView(this@FlowDictationIME).apply {
                text = "0"; setTextColor(Color.WHITE); textSize = 32f; gravity = Gravity.RIGHT; setPadding(20, 20, 20, 20)
            }
            addView(calcDisplay)
            
            val grid = arrayOf(arrayOf("7","8","9","/"), arrayOf("4","5","6","*"), arrayOf("1","2","3","-"), arrayOf("C","0","=","+"))
            for (row in grid) {
                val r = LinearLayout(this@FlowDictationIME).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 4f }
                for (btn in row) {
                    r.addView(createKeyButton(btn, isSpecial = false, weight = 1f) {
                        if (btn == "C") currentCalcText = ""
                        else if (btn == "=") evalMath()
                        else currentCalcText += btn
                        calcDisplay.text = if (currentCalcText.isEmpty()) "0" else currentCalcText
                    })
                }
                addView(r)
            }
            addView(createKeyButton("Insert", isSpecial = true, weight = 4f) { currentInputConnection?.commitText(calcDisplay.text, 1); toggleCalculatorMode() })
        }
    }

    private fun evalMath() {
        try {
            val res = currentCalcText.split(Regex("(?<=[-+*/])|(?=[-+*/])")).filter { it.isNotEmpty() }
            var total = res[0].toDouble()
            var op = ""
            for (i in 1 until res.size) {
                val token = res[i]
                if (token in listOf("+","-","*","/")) op = token
                else {
                    val num = token.toDouble()
                    total = when(op) { "+" -> total + num; "-" -> total - num; "*" -> total * num; "/" -> total / num; else -> total }
                }
            }
            currentCalcText = total.toString()
        } catch(e: Exception) { currentCalcText = "Error" }
    }

    private fun updateShiftState() {
        for (view in keyViews) {
            val t = view.text.toString()
            if (t.length == 1 && t[0].isLetter()) {
                view.text = if (isShifted) t.uppercase() else t.lowercase()
            }
        }
    }

    private fun toggleSymbolMode() {
        if (qwertyContainer.visibility == View.VISIBLE || deepSymbolContainer.visibility == View.VISIBLE) {
            qwertyContainer.visibility = View.GONE; deepSymbolContainer.visibility = View.GONE; symbolContainer.visibility = View.VISIBLE
        } else {
            qwertyContainer.visibility = View.VISIBLE; symbolContainer.visibility = View.GONE; deepSymbolContainer.visibility = View.GONE
        }
    }
    private fun toggleDeepSymbolMode() {
        if (symbolContainer.visibility == View.VISIBLE) {
            symbolContainer.visibility = View.GONE; deepSymbolContainer.visibility = View.VISIBLE
        } else {
            deepSymbolContainer.visibility = View.GONE; symbolContainer.visibility = View.VISIBLE
        }
    }
    private fun toggleCalculatorMode() {
        if (calcContainer.visibility == View.GONE) {
            qwertyContainer.visibility = View.GONE; symbolContainer.visibility = View.GONE; deepSymbolContainer.visibility = View.GONE; calcContainer.visibility = View.VISIBLE
        } else {
            calcContainer.visibility = View.GONE; qwertyContainer.visibility = View.VISIBLE
        }
    }

    private fun createToolbarButton(textStr: String, bgColor: String, textColor: String, weight: Float, onClick: () -> Unit): TextView {
        val density = resources.displayMetrics.density
        return TextView(this).apply {
            text = textStr; setTextColor(Color.parseColor(textColor)); textSize = 12f; gravity = Gravity.CENTER
            background = GradientDrawable().apply { setColor(Color.parseColor(bgColor)); cornerRadius = 12f * density }
            layoutParams = LinearLayout.LayoutParams(0, (38 * density).toInt(), weight).apply { setMargins((1*density).toInt(), (1*density).toInt(), (1*density).toInt(), (1*density).toInt()) }
            setOnClickListener { onClick() }
        }
    }

    private fun createKeyButton(textStr: String, isSpecial: Boolean, weight: Float = 1f, subscript: String = "", bgColor: String? = null, textColor: String? = null, longPressAction: (() -> Unit)? = null, onClick: () -> Unit): RelativeLayout {
        val density = resources.displayMetrics.density
        val defaultColor = bgColor ?: if (isSpecial) "#303030" else "#404040"
        return RelativeLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, (42 * density).toInt(), weight).apply { setMargins((2*density).toInt(), (4*density).toInt(), (2*density).toInt(), (4*density).toInt()) }
            background = GradientDrawable().apply { setColor(Color.parseColor(defaultColor)); cornerRadius = 6f * density }
            val mainText = TextView(this@FlowDictationIME).apply {
                text = textStr; setTextColor(Color.parseColor(textColor ?: "#FFFFFF")); textSize = if(isSpecial) 16f else 22f; gravity = Gravity.CENTER
                layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            }
            if (!isSpecial) keyViews.add(mainText)
            addView(mainText)
            
            if (subscript.isNotEmpty()) {
                addView(TextView(this@FlowDictationIME).apply {
                    text = subscript; setTextColor(Color.parseColor("#999999")); textSize = 11f
                    layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                        addRule(RelativeLayout.ALIGN_PARENT_TOP); addRule(RelativeLayout.ALIGN_PARENT_RIGHT); setMargins(0, (2 * density).toInt(), (4 * density).toInt(), 0)
                    }
                })
            }
            
            setOnTouchListener { v, event ->
                when(event.action) {
                    MotionEvent.ACTION_DOWN -> v.background = GradientDrawable().apply { setColor(Color.parseColor("#606060")); cornerRadius = 6f * density }
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> v.background = GradientDrawable().apply { setColor(Color.parseColor(defaultColor)); cornerRadius = 6f * density }
                }
                false
            }
            
            setOnClickListener { onClick() }
            if (longPressAction != null) {
                setOnLongClickListener { longPressAction(); true }
            }
        }
    }

    private fun createBackspaceButton(weight: Float): RelativeLayout {
        val density = resources.displayMetrics.density
        return RelativeLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, (42 * density).toInt(), weight).apply { setMargins((2*density).toInt(), (4*density).toInt(), (2*density).toInt(), (4*density).toInt()) }
            background = GradientDrawable().apply { setColor(Color.parseColor("#303030")); cornerRadius = 6f * density }
            addView(TextView(this@FlowDictationIME).apply { text = "⌫"; setTextColor(Color.WHITE); textSize = 20f; gravity = Gravity.CENTER; layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT) })
            
            var handler = Handler(Looper.getMainLooper())
            var runnable = object : Runnable { override fun run() { currentInputConnection?.deleteSurroundingText(1, 0); handler.postDelayed(this, 100) } }
            
            setOnTouchListener { v, event ->
                if (event.action == MotionEvent.ACTION_DOWN) {
                    currentInputConnection?.deleteSurroundingText(1, 0)
                    handler.postDelayed(runnable, 400)
                } else if (event.action == MotionEvent.ACTION_UP || event.action == MotionEvent.ACTION_CANCEL) {
                    handler.removeCallbacks(runnable)
                }
                true
            }
        }
    }

    private fun createSpacebarDictationButton(weight: Float): RelativeLayout {
        val density = resources.displayMetrics.density
        return RelativeLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, (42 * density).toInt(), weight).apply { setMargins((2*density).toInt(), (4*density).toInt(), (2*density).toInt(), (4*density).toInt()) }
            background = GradientDrawable().apply { setColor(Color.parseColor("#404040")); cornerRadius = 6f * density }
            addView(TextView(this@FlowDictationIME).apply { text = "Space"; setTextColor(Color.WHITE); textSize = 16f; gravity = Gravity.CENTER; layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT) })
            setOnClickListener { currentInputConnection?.commitText(" ", 1) }
            setOnLongClickListener { isOmniMode = false; toggleDictation(); true }
        }
    }

    private fun toggleDictation() {
        if (isRecording) {
            isRecording = false
            updateAllDictationUI()
            stopAudioCaptureAndProcess()
        } else {
            isRecording = true
            updateAllDictationUI()
            startAudioCapture()
        }
    }

    private fun updateAllDictationUI() {
        val density = resources.displayMetrics.density
        if (isRecording) {
            val bgColor = if (isOmniMode) "#55FFAA" else "#2A2A2A"
            dictationButton.background = GradientDrawable().apply { setColor(Color.parseColor(bgColor)); cornerRadius = 12f * density }
            if (recordingAnimator == null) {
                val scaleX = PropertyValuesHolder.ofFloat(View.SCALE_X, 1f, 1.1f)
                val scaleY = PropertyValuesHolder.ofFloat(View.SCALE_Y, 1f, 1.1f)
                recordingAnimator = ObjectAnimator.ofPropertyValuesHolder(dictationButton, scaleX, scaleY).apply { duration = 800; repeatMode = ObjectAnimator.REVERSE; repeatCount = ObjectAnimator.INFINITE; start() }
            } else { recordingAnimator?.start() }
            
            spacebarButton.background = GradientDrawable().apply { setColor(Color.parseColor(bgColor)); cornerRadius = 6f * density }
            if (spacebarAnimator == null) {
                val scaleX = PropertyValuesHolder.ofFloat(View.SCALE_X, 1f, 1.1f)
                val scaleY = PropertyValuesHolder.ofFloat(View.SCALE_Y, 1f, 1.1f)
                spacebarAnimator = ObjectAnimator.ofPropertyValuesHolder(spacebarButton, scaleX, scaleY).apply { duration = 800; repeatCount = ObjectAnimator.INFINITE; repeatMode = ObjectAnimator.REVERSE; start() }
            } else { spacebarAnimator?.start() }
        } else {
            recordingAnimator?.cancel(); dictationButton.scaleX = 1f; dictationButton.scaleY = 1f
            dictationButton.background = GradientDrawable().apply { setColor(Color.parseColor("#2A2A2A")); cornerRadius = 12f * density }
            spacebarAnimator?.cancel(); spacebarButton.scaleX = 1f; spacebarButton.scaleY = 1f
            spacebarButton.background = GradientDrawable().apply { setColor(Color.parseColor("#404040")); cornerRadius = 6f * density }
            isOmniMode = false
        }
    }

    private fun startAudioCapture() {
        audioBuffer.reset()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) return
        audioRecord = AudioRecord(1, sampleRate, 16, 2, bufferSize)
        audioRecord?.startRecording()
        recordingThread = Thread {
            val data = ByteArray(bufferSize)
            while (isRecording) {
                val read = audioRecord?.read(data, 0, data.size) ?: 0
                if (read > 0) audioBuffer.write(data, 0, read)
            }
        }
        recordingThread?.start()
    }

    private fun stopAudioCaptureAndProcess() {
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
        
        val pcmData = audioBuffer.toByteArray()
        if (pcmData.isEmpty()) return
        
        val wavHeader = createWavHeader(pcmData.size, sampleRate, 1, 16)
        val wavData = ByteArray(wavHeader.size + pcmData.size)
        System.arraycopy(wavHeader, 0, wavData, 0, wavHeader.size)
        System.arraycopy(pcmData, 0, wavData, wavHeader.size, pcmData.size)
        
        coroutineScope.launch {
            if (isOmniMode) {
                processOmniMode(wavData)
            } else {
                val transcribedText = transcribeWithGroq(wavData)
                if (transcribedText.isNotBlank()) {
                    val formatted = formatWithGemini(transcribedText)
                    currentInputConnection?.commitText(formatted + " ", 1)
                }
            }
        }
    }

    private fun createWavHeader(pcmDataLen: Int, sampleRate: Int, channels: Int, bitRate: Int): ByteArray {
        val totalDataLen = pcmDataLen + 36
        val byteRate = sampleRate * channels * (bitRate / 8)
        val header = ByteArray(44)
        val b = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN)
        b.put("RIFF".toByteArray())
        b.putInt(totalDataLen)
        b.put("WAVE".toByteArray())
        b.put("fmt ".toByteArray())
        b.putInt(16)
        b.putShort(1.toShort())
        b.putShort(channels.toShort())
        b.putInt(sampleRate)
        b.putInt(byteRate)
        b.putShort((channels * (bitRate / 8)).toShort())
        b.putShort(bitRate.toShort())
        b.put("data".toByteArray())
        b.putInt(pcmDataLen)
        return header
    }

    private suspend fun transcribeWithGroq(wavData: ByteArray): String = withContext(Dispatchers.IO) {
        try {
            val client = OkHttpClient()
            val requestBody = MultipartBody.Builder().setType(MultipartBody.FORM)
                .addFormDataPart("file", "audio.wav", wavData.toRequestBody("audio/wav".toMediaType()))
                .addFormDataPart("model", "whisper-large-v3")
                .build()
            val request = Request.Builder()
                .url("https://api.groq.com/openai/v1/audio/transcriptions")
                .header("Authorization", "Bearer $groqApiKey")
                .post(requestBody)
                .build()
            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                return@withContext JSONObject(response.body?.string() ?: "").getString("text")
            }
        } catch (e: Exception) {}
        return@withContext ""
    }

    private suspend fun formatWithGemini(transcribedText: String): String = withContext(Dispatchers.IO) {
        try {
            val model = GenerativeModel("gemini-1.5-flash", geminiApiKey, systemInstruction = content { text("Format dictation with correct punctuation. Strictly follow: " + globalDictionary) })
            return@withContext model.generateContent(transcribedText).text?.trim() ?: transcribedText
        } catch (e: Exception) {}
        return@withContext transcribedText
    }

    private fun scanPlacardWithGemini(path: String) {
        coroutineScope.launch {
            try {
                val bitmap = BitmapFactory.decodeFile(path)
                val model = GenerativeModel("gemini-1.5-flash", geminiApiKey, systemInstruction = content { text("Extract all serial numbers and text from this placard") })
                val resp = model.generateContent(content { image(bitmap) }).text ?: ""
                currentInputConnection?.commitText(resp, 1)
            } catch (e: Exception) {}
        }
    }

    private fun rewriteText() {
        val ic = currentInputConnection
        val text = ic?.getExtractedText(ExtractedTextRequest(), 0)?.text?.toString() ?: return
        coroutineScope.launch {
            try {
                val model = GenerativeModel("gemini-1.5-flash", geminiApiKey, systemInstruction = content { text("Rewrite this text professionally, fix grammar.") })
                val resp = model.generateContent(text).text ?: ""
                ic.deleteSurroundingText(10000, 10000)
                ic.commitText(resp, 1)
            } catch (e: Exception) {}
        }
    }

    private suspend fun processOmniMode(wavData: ByteArray) {
        val query = transcribeWithGroq(wavData)
        if (query.isBlank()) return
        
        // Check Cloud Commands first
        for ((trigger, action) in omniCommands) {
            if (query.lowercase().contains(trigger)) {
                currentInputConnection?.commitText(action, 1)
                return
            }
        }

        // Native Contacts search tool implementation
        fun getContact(name: String): String {
            val uri = android.provider.ContactsContract.CommonDataKinds.Phone.CONTENT_URI
            val proj = arrayOf(android.provider.ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME, android.provider.ContactsContract.CommonDataKinds.Phone.NUMBER)
            val cursor = contentResolver.query(uri, proj, "${android.provider.ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} LIKE ?", arrayOf("%$name%"), null)
            var contactInfo = ""
            if (cursor != null && cursor.moveToFirst()) {
                contactInfo = cursor.getString(0) + ": " + cursor.getString(1)
            }
            cursor?.close()
            return contactInfo
        }

        // LLM Tool routing
        val prompt = "You are an Omni Agent on an Android keyboard. User requested: '$query'. If asking for a contact, return JSON: {\"tool\":\"contacts\", \"arg\":\"[name]\"}. Otherwise return text."
        try {
            val model = GenerativeModel("gemini-1.5-flash", geminiApiKey)
            val resp = model.generateContent(prompt).text ?: ""
            if (resp.contains("contacts")) {
                try {
                    val json = JSONObject(resp.substring(resp.indexOf("{"), resp.lastIndexOf("}") + 1))
                    val contactStr = getContact(json.getString("arg"))
                    if (contactStr.isNotEmpty()) currentInputConnection?.commitText(contactStr, 1) else currentInputConnection?.commitText("Contact not found.", 1)
                } catch (e: Exception) { currentInputConnection?.commitText("Contacts tool error.", 1) }
            } else {
                currentInputConnection?.commitText(resp, 1)
            }
        } catch (e: Exception) {}
    }
}
