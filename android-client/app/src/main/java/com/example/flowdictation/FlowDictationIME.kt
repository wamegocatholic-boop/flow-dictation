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
    private lateinit var dictationButtonContainer: RelativeLayout
    private lateinit var calcDisplay: TextView
    
    private lateinit var mainVisualizer: AudioVisualizerView
    private lateinit var spacebarVisualizer: AudioVisualizerView
    
    private var isRecording = false
    private var isOmniMode = false
    private var isGoogleSearchMode = false
    private var isShifted = false
    private var currentCalcText = ""

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

    inner class AudioVisualizerView(context: Context) : View(context) {
        var amplitudes = FloatArray(7) { 0.2f }
        var isRecording = false
        var activeColor = Color.WHITE
        var idleColor = Color.parseColor("#888888")
        private val paint = android.graphics.Paint().apply {
            style = android.graphics.Paint.Style.FILL
            strokeCap = android.graphics.Paint.Cap.ROUND
        }
        
        override fun onDraw(canvas: android.graphics.Canvas) {
            super.onDraw(canvas)
            val w = width.toFloat()
            val h = height.toFloat()
            val numBars = amplitudes.size
            val spacing = 12f
            val totalSpacing = spacing * (numBars - 1)
            val barWidth = 6f * resources.displayMetrics.density
            paint.strokeWidth = barWidth
            val totalWidth = (barWidth * numBars) + totalSpacing
            var startX = (w - totalWidth) / 2f + (barWidth / 2f)
            
            paint.color = if (isRecording) activeColor else idleColor
            val staticAmps = listOf(0.3f, 0.6f, 0.9f, 1.0f, 0.9f, 0.6f, 0.3f)
            
            for (i in amplitudes.indices) {
                val amp = if (isRecording) amplitudes[i] else staticAmps[i]
                val barHeight = Math.max(barWidth, h * amp * 0.9f)
                val top = (h - barHeight) / 2f
                val bottom = top + barHeight
                canvas.drawLine(startX, top, startX, bottom, paint)
                startX += barWidth + spacing
            }
        }
    }

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

        dictationButtonContainer = RelativeLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, (80 * density).toInt(), 1f).apply { setMargins((1 * density).toInt(), (1 * density).toInt(), (1 * density).toInt(), (1 * density).toInt()) }
            background = GradientDrawable().apply { setColor(Color.parseColor("#2A2A2A")); cornerRadius = 12f * density }
            
            mainVisualizer = AudioVisualizerView(this@FlowDictationIME).apply {
                layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            }
            addView(mainVisualizer)
            
            setOnTouchListener { v, event ->
                when(event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#404040")); cornerRadius = 12f * density }
                    }
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                        val bgColor = if (isRecording) { if (isOmniMode || isGoogleSearchMode) "#55FFAA" else "#2A2A2A" } else "#2A2A2A"
                        v.background = GradientDrawable().apply { setColor(Color.parseColor(bgColor)); cornerRadius = 12f * density }
                    }
                }
                false
            }
            
            setOnClickListener {
                if (ContextCompat.checkSelfPermission(this@FlowDictationIME, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) toggleDictation()
            }
        }
        toolbarContainer.addView(dictationButtonContainer)

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
        
        val btnGoogle = createToolbarButton("🔍 Google", "#1E1E1E", "#AA55FF", weight = 1f) {
            isGoogleSearchMode = true
            toggleDictation()
        }
        val btnOmni = createToolbarButton("🪄 Omni", "#1E1E1E", "#55FFAA", weight = 1f) {
            isOmniMode = true
            toggleDictation()
        }
        val btnCalc = createToolbarButton("🧮 Calc", "#1E1E1E", "#FFAA55", weight = 1f) { toggleCalculatorMode() }
        val btnRewrite = createToolbarButton("✨ Fix", "#1E1E1E", "#FF55AA", weight = 1f) { rewriteText() }
        
        toolbarRow2.addView(btnGoogle)
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
        val longPressTexts = listOf(
            "Thanks,",
            "Zach",
            "Zach Teske\nFUMA Insurance\nzteske@fumainsurance.com\n785-456-3505",
            "zteske@fumainsurance.com",
            "zeteske@gmail.com",
            "https://quickquote-app-sable.vercel.app/?mode=customQuote&config=eyJjYXRzIjpbXSwiaGlkZGVuIjpbXX0=&first=&last=",
            "🙂",
            "😛",
            "😂",
            "👎"
        )
        for (i in 0..9) {
            val lpText = longPressTexts[i]
            val dispSub = if (i > 5) lpText else ""
            r0.addView(createKeyButton(numbers[i], isSpecial = false, subscript = dispSub, longPressAction = { currentInputConnection?.commitText(lpText, 1) }) {
                currentInputConnection?.commitText(if (isShifted) numbers[i].uppercase() else numbers[i], 1)
                if (isShifted) { isShifted = false; updateShiftState() }
            })
        }
        container.addView(r0)

        val r1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        val qrow = listOf("q","w","e","r","t","y","u","i","o","p")
        val qrowSub = listOf("%","\\","|","=","[","]","<",">","{","}")
        for (i in qrow.indices) {
            val k = qrow[i]
            val sub = qrowSub[i]
            r1.addView(createKeyButton(k, isSpecial = false, subscript = sub, longPressAction = { currentInputConnection?.commitText(sub, 1) }) {
                currentInputConnection?.commitText(if (isShifted) k.uppercase() else k, 1)
                if (isShifted) { isShifted = false; updateShiftState() }
            })
        }
        container.addView(r1)

        val r2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        r2.addView(View(this).apply { layoutParams = LinearLayout.LayoutParams(0, 1, 0.5f) })
        val arow = listOf("a","s","d","f","g","h","j","k","l")
        val arowSub = listOf("@","#","$","_","&","-","+","(",")")
        for (i in arow.indices) {
            val k = arow[i]
            val sub = arowSub[i]
            r2.addView(createKeyButton(k, isSpecial = false, subscript = sub, longPressAction = { currentInputConnection?.commitText(sub, 1) }) {
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
        val zrowSub = listOf("*","\"","'",":",";","!","?")
        for (i in zrow.indices) {
            val k = zrow[i]
            val sub = zrowSub[i]
            r3.addView(createKeyButton(k, isSpecial = false, subscript = sub, longPressAction = { currentInputConnection?.commitText(sub, 1) }) {
                currentInputConnection?.commitText(if (isShifted) k.uppercase() else k, 1)
                if (isShifted) { isShifted = false; updateShiftState() }
            })
        }
        r3.addView(createBackspaceButton(1.5f))
        container.addView(r3)

        val bottomRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; isBaselineAligned = false; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 10f }
        bottomRow.addView(createKeyButton("?123", isSpecial = true, weight = 1.5f) { toggleSymbolMode() })
        bottomRow.addView(createKeyButton(",", isSpecial = true, weight = 1f, subscript = "👍", longPressAction = { currentInputConnection?.commitText("👍", 1) }) { currentInputConnection?.commitText(",", 1) })
        bottomRow.addView(createKeyButton("📸", isSpecial = true, weight = 1f) { 
            val intent = Intent(this, CameraCaptureActivity::class.java); intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK); startActivity(intent)
        })
        
        spacebarButton = createSpacebarDictationButton(weight = 4f)
        bottomRow.addView(spacebarButton)
        
        bottomRow.addView(createKeyButton(".", isSpecial = true, weight = 1f, subscript = "🤷‍♂️", longPressAction = { currentInputConnection?.commitText("🤷‍♂️", 1) }) { currentInputConnection?.commitText(".", 1) })
        bottomRow.addView(createKeyButton("⏎", isSpecial = true, weight = 1.5f, bgColor = "#4A90E2", textColor = "#FFFFFF") {
            val action = currentInputEditorInfo.imeOptions and android.view.inputmethod.EditorInfo.IME_MASK_ACTION
            if (action == android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH || action == android.view.inputmethod.EditorInfo.IME_ACTION_GO) {
                currentInputConnection?.performEditorAction(action)
            } else {
                currentInputConnection?.commitText("\n", 1)
            }
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
        r3.addView(createKeyButton("↵", isSpecial = true, weight = 1.5f, bgColor = "#4A90E2", textColor = "#FFFFFF") {
            val action = currentInputEditorInfo.imeOptions and android.view.inputmethod.EditorInfo.IME_MASK_ACTION
            if (action == android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH || action == android.view.inputmethod.EditorInfo.IME_ACTION_GO) {
                currentInputConnection?.performEditorAction(action)
            } else {
                currentInputConnection?.commitText("\n", 1)
            }
        })
        
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
        r3.addView(createKeyButton("↵", isSpecial = true, weight = 1.5f, bgColor = "#4A90E2", textColor = "#FFFFFF") {
            val action = currentInputEditorInfo.imeOptions and android.view.inputmethod.EditorInfo.IME_MASK_ACTION
            if (action == android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH || action == android.view.inputmethod.EditorInfo.IME_ACTION_GO) {
                currentInputConnection?.performEditorAction(action)
            } else {
                currentInputConnection?.commitText("\n", 1)
            }
        })
        
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
            val calcBottomRow = LinearLayout(this@FlowDictationIME).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); weightSum = 2f }
            calcBottomRow.addView(createKeyButton("Return", isSpecial = true, weight = 1f) { toggleCalculatorMode() })
            calcBottomRow.addView(createKeyButton("Insert Result", isSpecial = true, weight = 1f, bgColor = "#4A90E2", textColor = "#FFFFFF") { currentInputConnection?.commitText(calcDisplay.text, 1); toggleCalculatorMode() })
            addView(calcBottomRow)
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
            
            setOnTouchListener { v, event ->
                when(event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#404040")); cornerRadius = 12f * density }
                    }
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> v.background = GradientDrawable().apply { setColor(Color.parseColor(bgColor)); cornerRadius = 12f * density }
                }
                false
            }
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
                text = textStr; setTextColor(Color.parseColor(textColor ?: "#FFFFFF")); textSize = if(textStr == "⏎") 34f else if(isSpecial) 16f else 22f; gravity = Gravity.CENTER
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
                    MotionEvent.ACTION_DOWN -> {
                        v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#606060")); cornerRadius = 6f * density }
                    }
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
            var heldTime = 0L
            var runnable = object : Runnable { 
                override fun run() { 
                    heldTime += 100
                    if (heldTime > 500) {
                        val textBefore = currentInputConnection?.getTextBeforeCursor(50, 0) ?: ""
                        val lastSpace = textBefore.trimEnd().lastIndexOf(' ')
                        if (lastSpace != -1) {
                            val toDelete = textBefore.length - lastSpace
                            currentInputConnection?.deleteSurroundingText(toDelete, 0)
                        } else {
                            currentInputConnection?.deleteSurroundingText(textBefore.length, 0)
                        }
                        handler.postDelayed(this, 350) 
                    } else {
                        currentInputConnection?.deleteSurroundingText(1, 0) 
                        handler.postDelayed(this, 100) 
                    }
                } 
            }
            
            setOnTouchListener { v, event ->
                if (event.action == MotionEvent.ACTION_DOWN) {
                    v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                    v.background = GradientDrawable().apply { setColor(Color.parseColor("#606060")); cornerRadius = 6f * density }
                    heldTime = 0L
                    currentInputConnection?.deleteSurroundingText(1, 0)
                    handler.postDelayed(runnable, 400)
                } else if (event.action == MotionEvent.ACTION_UP || event.action == MotionEvent.ACTION_CANCEL) {
                    v.background = GradientDrawable().apply { setColor(Color.parseColor("#303030")); cornerRadius = 6f * density }
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
            
            spacebarVisualizer = AudioVisualizerView(this@FlowDictationIME).apply {
                layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
                alpha = 0.2f
            }
            addView(spacebarVisualizer)
            
            addView(TextView(this@FlowDictationIME).apply { text = "Space"; setTextColor(Color.WHITE); textSize = 16f; gravity = Gravity.CENTER; layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT) })
            
            var handler = Handler(Looper.getMainLooper())
            var isSpacebarRecording = false
            var longPressRunnable = Runnable {
                isSpacebarRecording = true
                isOmniMode = false
                if (!isRecording) toggleDictation()
            }
            
            setOnTouchListener { v, event ->
                when(event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#606060")); cornerRadius = 6f * density }
                        isSpacebarRecording = false
                        handler.postDelayed(longPressRunnable, 400)
                    }
                    MotionEvent.ACTION_UP -> {
                        handler.removeCallbacks(longPressRunnable)
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#404040")); cornerRadius = 6f * density }
                        if (isSpacebarRecording) {
                            if (isRecording) toggleDictation()
                        } else {
                            currentInputConnection?.commitText(" ", 1)
                        }
                    }
                    MotionEvent.ACTION_CANCEL -> {
                        handler.removeCallbacks(longPressRunnable)
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#404040")); cornerRadius = 6f * density }
                        if (isSpacebarRecording && isRecording) toggleDictation()
                    }
                }
                true
            }
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
            val bgColor = if (isOmniMode || isGoogleSearchMode) "#55FFAA" else "#2A2A2A"
            val visColor = if (isOmniMode || isGoogleSearchMode) Color.parseColor("#000000") else Color.WHITE
            
            dictationButtonContainer.background = GradientDrawable().apply { setColor(Color.parseColor(bgColor)); cornerRadius = 12f * density }
            mainVisualizer.isRecording = true
            mainVisualizer.activeColor = visColor
            mainVisualizer.invalidate()
            
            spacebarButton.background = GradientDrawable().apply { setColor(Color.parseColor(bgColor)); cornerRadius = 6f * density }
            spacebarVisualizer.isRecording = true
            spacebarVisualizer.activeColor = visColor
            spacebarVisualizer.alpha = 0.5f
            spacebarVisualizer.invalidate()
        } else {
            dictationButtonContainer.background = GradientDrawable().apply { setColor(Color.parseColor("#2A2A2A")); cornerRadius = 12f * density }
            mainVisualizer.isRecording = false
            mainVisualizer.invalidate()
            
            spacebarButton.background = GradientDrawable().apply { setColor(Color.parseColor("#404040")); cornerRadius = 6f * density }
            spacebarVisualizer.isRecording = false
            spacebarVisualizer.alpha = 0.2f
            spacebarVisualizer.invalidate()
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
                if (read > 0) {
                    audioBuffer.write(data, 0, read)
                    var sum = 0.0
                    for (i in 0 until read step 2) {
                        if (i+1 < read) {
                            val sample = (data[i].toInt() and 0xFF) or (data[i+1].toInt() shl 8)
                            val s = sample.toShort().toFloat()
                            sum += (s * s)
                        }
                    }
                    val rms = Math.sqrt(sum / (read / 2.0)).toFloat()
                    val normalizedAmp = Math.min(1f, rms / 2500f) // Boosted sensitivity for better animation
                    
                    for (i in 0 until 6) {
                        mainVisualizer.amplitudes[i] = mainVisualizer.amplitudes[i+1]
                    }
                    mainVisualizer.amplitudes[6] = normalizedAmp
                    
                    mainVisualizer.post { mainVisualizer.invalidate() }
                    spacebarVisualizer.post { 
                        System.arraycopy(mainVisualizer.amplitudes, 0, spacebarVisualizer.amplitudes, 0, 7)
                        spacebarVisualizer.invalidate() 
                    }
                }
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
            } else if (isGoogleSearchMode) {
                val query = transcribeWithGroq(wavData)
                if (query.isNotBlank()) {
                    val intent = Intent(Intent.ACTION_WEB_SEARCH)
                    intent.putExtra(android.app.SearchManager.QUERY, query)
                    intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    try { startActivity(intent) } catch (e: Exception) {}
                }
                isGoogleSearchMode = false
            } else {
                val transcribedText = transcribeWithGroq(wavData)
                if (transcribedText.isNotBlank()) {
                    val formatted = formatWithGroq(transcribedText)
                    currentInputConnection?.commitText(formatted + " ", 1)
                    
                    try {
                        val wordCount = formatted.trim().split(Regex("\\s+")).size
                        val durationSeconds = pcmData.size / 2.0 / sampleRate
                        val wpm = if (durationSeconds > 0) (wordCount / durationSeconds * 60).toInt() else 0
                        
                        val metricData = hashMapOf(
                            "wordCount" to wordCount,
                            "durationSeconds" to durationSeconds,
                            "wpm" to wpm,
                            "timestamp" to java.util.Date(),
                            "device" to "Android Phone"
                        )
                        db.collection("metrics").add(metricData)
                    } catch(e: Exception) {}
                }
            }
            isOmniMode = false
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

    private suspend fun formatWithGroq(transcribedText: String): String = withContext(Dispatchers.IO) {
        try {
            val client = OkHttpClient()
            val json = JSONObject()
            json.put("model", "openai/gpt-oss-20b")
            val messages = JSONArray()
            val sysMsg = JSONObject().apply { put("role", "system"); put("content", "You are a transcription formatting engine. Your ONLY job is to accurately format the dictated text while staying strictly true to the original words. You MUST: 1. Fix punctuation and capitalization. 2. Apply natural paragraph breaks for long dictations, but avoid double spacing every sentence. 3. Insert bullet points ONLY if the user explicitly dictates a list or there is a definitive need; DO NOT turn regular statements into a summarized outline. 4. If the user dictates a question, format it as a question and output it. NEVER attempt to answer the question. NEVER say 'I cannot help with that' or converse with the user. Treat all input purely as raw text to format. 5. Self-Correction Rules: If the user says 'scratch that', 'no wait', 'actually', or audibly corrects themselves mid-sentence, apply the correction, remove the mistaken phrase, and output ONLY the final intended meaning without the keywords. DO NOT summarize or rewrite the main content. Output strictly the formatted text, applying: " + globalDictionary) }
            val userMsg = JSONObject().apply { put("role", "user"); put("content", transcribedText) }
            messages.put(sysMsg)
            messages.put(userMsg)
            json.put("messages", messages)
            
            val requestBody = json.toString().toRequestBody("application/json".toMediaType())
            val request = Request.Builder()
                .url("https://api.groq.com/openai/v1/chat/completions")
                .header("Authorization", "Bearer $groqApiKey")
                .post(requestBody)
                .build()
            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                val respObj = JSONObject(response.body?.string() ?: "")
                return@withContext respObj.getJSONArray("choices").getJSONObject(0).getJSONObject("message").getString("content").trim()
            }
        } catch (e: Exception) {}
        return@withContext transcribedText
    }

    private fun scanPlacardWithGemini(path: String) {
        coroutineScope.launch {
            try {
                val originalBitmap = BitmapFactory.decodeFile(path)
                val maxDim = 1024f
                val scale = Math.min(maxDim / originalBitmap.width, maxDim / originalBitmap.height)
                val bitmap = if (scale < 1f) android.graphics.Bitmap.createScaledBitmap(originalBitmap, (originalBitmap.width * scale).toInt(), (originalBitmap.height * scale).toInt(), true) else originalBitmap
                
                val model = GenerativeModel("gemini-3.5-flash", geminiApiKey, systemInstruction = content { text("Analyze this image and extract the model number, serial number, make, and build year. If and only if it is an AC unit, include the tonnage. Output ONLY the raw values separated by newlines. Do not use any markdown (no asterisks or bold text) and do not include any introductory sentences.") })
                val resp = model.generateContent(content { image(bitmap) }).text ?: ""
                currentInputConnection?.commitText(resp, 1)
            } catch (e: Exception) {}
        }
    }

    private fun rewriteText() {
        val ic = currentInputConnection
        val text = ic?.getExtractedText(ExtractedTextRequest(), 0)?.text?.toString() ?: return
        coroutineScope.launch(Dispatchers.IO) {
            try {
                val sysPrompt = "You are a professional text formatter. Your task is to clean up the following text by fixing spelling, grammar, punctuation, and capitalization errors. You MUST keep the text as close to the original wording as possible. Do not completely rewrite it, do not use synonyms to replace the user's words, and do not change the core meaning. Only make the necessary functional cleanups so it sounds professional and grammatically correct. Output strictly the fixed text."
                val model = com.google.ai.client.generativeai.GenerativeModel("gemini-3.5-flash", geminiApiKey, systemInstruction = com.google.ai.client.generativeai.type.content { text(sysPrompt) })
                val resp = model.generateContent(text).text?.trim() ?: "No response."
                withContext(Dispatchers.Main) {
                    ic.deleteSurroundingText(10000, 10000)
                    ic.commitText(resp + " ", 1)
                }
            } catch(e: Exception) {
                withContext(Dispatchers.Main) {
                    ic.commitText("Error: ${e.message} ", 1)
                }
            }
        }
    }

    private fun pasteLatestGalleryImage() {
        coroutineScope.launch(Dispatchers.IO) {
            val proj = arrayOf(MediaStore.Images.Media._ID)
            val sortOrder = "${MediaStore.Images.Media.DATE_ADDED} DESC"
            val cursor = contentResolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, proj, null, null, sortOrder)
            var uri: Uri? = null
            if (cursor != null && cursor.moveToFirst()) {
                val id = cursor.getLong(0)
                uri = android.content.ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)
            }
            cursor?.close()
            
            withContext(Dispatchers.Main) {
                if (uri != null) {
                    val description = android.content.ClipDescription("Latest Image", arrayOf("image/*", "image/jpeg", "image/png"))
                    val contentInfo = android.view.inputmethod.InputContentInfo(uri, description)
                    val success = currentInputConnection?.commitContent(contentInfo, android.view.inputmethod.InputConnection.INPUT_CONTENT_GRANT_READ_URI_PERMISSION, null)
                    if (success != true) {
                        currentInputConnection?.commitText("App does not support pasting images.", 1)
                    }
                } else {
                    currentInputConnection?.commitText("No image found.", 1)
                }
            }
        }
    }

    private suspend fun processOmniMode(wavData: ByteArray) {
        val query = transcribeWithGroq(wavData)
        if (query.isBlank()) return
        
        for ((trigger, action) in omniCommands) {
            if (query.lowercase().contains(trigger)) {
                currentInputConnection?.commitText(action, 1)
                return
            }
        }

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

        val prompt = "You are an Omni Agent acting as an Android keyboard. User requested: '$query'. Do NOT echo the user's command. Act as the user's hands. Provide ONLY the raw requested answer. Absolutely no conversational filler, no introductory text, and no markdown. If asked a math question, provide only the numeric answer (e.g., '108'). If asked to type or paste something, output ONLY the exact text they want generated. If asking for a contact, return JSON: {\"tool\":\"contacts\", \"arg\":\"[name]\"}."
        try {
            val sysPrompt = "You are an intelligent assistant. Answer factual queries, solve math, and follow commands briefly. You have access to these contacts/commands: " + omniCommands.entries.joinToString { it.key + ":" + it.value } + " Use them if asked. NEVER refuse to help."
            val model = com.google.ai.client.generativeai.GenerativeModel("gemini-3.5-flash", geminiApiKey, systemInstruction = com.google.ai.client.generativeai.type.content { text(sysPrompt) })
            
            withContext(Dispatchers.IO) {
                val respObj = model.generateContent(prompt)
                val resp = respObj.text?.trim() ?: ""
                withContext(Dispatchers.Main) {
                    if (resp.contains("contacts")) {
                        try {
                            val parsed = JSONObject(resp.substring(resp.indexOf("{"), resp.lastIndexOf("}") + 1))
                            val contactStr = getContact(parsed.getString("arg"))
                            if (contactStr.isNotEmpty()) currentInputConnection?.commitText(contactStr, 1) else currentInputConnection?.commitText("Contact not found.", 1)
                        } catch (e: Exception) { currentInputConnection?.commitText("Contacts tool error.", 1) }
                    } else if (resp.contains("gallery")) {
                        pasteLatestGalleryImage()
                    } else {
                        currentInputConnection?.commitText(resp, 1)
                    }
                }
            }
        } catch (e: Exception) {
            withContext(Dispatchers.Main) { currentInputConnection?.commitText("Error: ${e.message}", 1) }
        }
    }
}
