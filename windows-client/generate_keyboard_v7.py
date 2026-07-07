import os

keys = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
    ['SHIFT', 'z', 'x', 'c', 'v', 'b', 'n', 'm', 'DEL']
]

long_press_map = {
    '1': 'zteske@fumainsurance.com',
    '2': 'zeteske@gmail.com',
    '3': 'Complete your quick insurance quote form here: https://quickquote-app-sable.vercel.app/?mode=client',
    '4': 'Please complete our full insurance quote application here: https://quickquote-app-sable.vercel.app/?mode=fullclient',
    '5': 'Submit your payment info here through our Secure FUMA Insurance link: https://quickquote-app-sable.vercel.app/?mode=payment',
    'z': '👍', 'x': '👎', 'c': '🙂', 'v': '😂', 'b': '🤪',
    'n': '!', 'm': '?'
}

subscript_map = {
    '1': '✉', '2': 'G', '3': 'Q1', '4': 'Q2', '5': '$',
    'z': '👍', 'x': '👎', 'c': '🙂', 'v': '😂', 'b': '🤪',
    'n': '!', 'm': '?'
}

out = []

out.append("""package com.example.flowdictation

import android.Manifest
import android.animation.ObjectAnimator
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

class FlowDictationIME : InputMethodService() {

    private lateinit var mainContainer: LinearLayout
    private lateinit var qwertyContainer: LinearLayout
    private lateinit var calcContainer: LinearLayout
    private lateinit var dictationButton: TextView
    private lateinit var calcDisplay: TextView
    
    private var isRecording = false
    private var isShifted = false
    private var currentCalcText = ""
    private var recordingAnimator: ObjectAnimator? = null

    private var audioRecord: AudioRecord? = null
    private var recordingThread: Thread? = null
    private val sampleRate = 16000
    private val bufferSize = AudioRecord.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
    private val audioBuffer = ByteArrayOutputStream()

    private val serviceJob = Job()
    private val coroutineScope = CoroutineScope(Dispatchers.Main + serviceJob)

    private val groqApiKey = ""
    private val geminiApiKey = ""
    
    private val keyViews = mutableListOf<TextView>()

    override fun onCreateInputView(): View {
        val density = resources.displayMetrics.density
        
        mainContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            setBackgroundColor(Color.parseColor("#0A0A0A"))
            setPadding(0, (5 * density).toInt(), 0, 0)
        }

        // --- AI Command Center (2 Rows) ---
        val toolbarRow1 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            weightSum = 5f
            setPadding((2 * density).toInt(), (2 * density).toInt(), (2 * density).toInt(), 0)
        }
        val toolbarRow2 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            weightSum = 4f
            setPadding((2 * density).toInt(), (2 * density).toInt(), (2 * density).toInt(), (5 * density).toInt())
        }
        
        dictationButton = createToolbarButton("🎤 Flow", "#2A2A2A", "#FFFFFF", weight = 1f) {
            if (ContextCompat.checkSelfPermission(this@FlowDictationIME, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) toggleDictation()
        }
        val btnPaste = createToolbarButton("📋 Paste", "#1E1E1E", "#AAAAAA", weight = 1f) {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.primaryClip?.getItemAt(0)?.text?.let { currentInputConnection?.commitText(it, 1) }
        }
        val btnSelectAll = createToolbarButton("🎯 Select", "#1E1E1E", "#FFFF55", weight = 1f) {
            val ic = currentInputConnection
            val text = ic?.getExtractedText(ExtractedTextRequest(), 0)?.text ?: return@createToolbarButton
            ic.setSelection(0, text.length)
        }
        val btnRewrite = createToolbarButton("✨ Fix", "#1E1E1E", "#55AAFF", weight = 1f) { rewriteText() }
        val btnNuke = createToolbarButton("💣 Nuke", "#1E1E1E", "#FF5555", weight = 1f) { currentInputConnection?.deleteSurroundingText(10000, 10000) }
        
        toolbarRow1.addView(dictationButton)
        toolbarRow1.addView(btnPaste)
        toolbarRow1.addView(btnSelectAll)
        toolbarRow1.addView(btnRewrite)
        toolbarRow1.addView(btnNuke)
        
        val btnGemini = createToolbarButton("🌌 Gemini", "#1E1E1E", "#AA55FF", weight = 1f) {
            try { 
                val intent = Intent(Intent.ACTION_VOICE_COMMAND)
                intent.setPackage("com.google.android.googlequicksearchbox")
                intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK
                startActivity(intent) 
            } catch (e: Exception) { Log.e("Flow", "Gemini Intent failed", e) }
        }
        val btnBixby = createToolbarButton("🎙 Bixby", "#1E1E1E", "#55FFAA", weight = 1f) {
            try { 
                val intent = Intent(Intent.ACTION_VOICE_COMMAND)
                intent.setPackage("com.samsung.android.bixby.agent")
                intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK
                startActivity(intent) 
            } catch (e: Exception) { Log.e("Flow", "Bixby Intent failed", e) }
        }
        val btnCalc = createToolbarButton("🧮 Calc", "#1E1E1E", "#FFAA55", weight = 1f) { toggleCalculatorMode() }
        val btnPhotos = createToolbarButton("🖼️ Photos", "#1E1E1E", "#FF55AA", weight = 1f) {
            try { startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_APP_GALLERY).apply { flags = Intent.FLAG_ACTIVITY_NEW_TASK }) } catch (e: Exception) {}
        }
        
        toolbarRow2.addView(btnGemini)
        toolbarRow2.addView(btnBixby)
        toolbarRow2.addView(btnCalc)
        toolbarRow2.addView(btnPhotos)

        mainContainer.addView(toolbarRow1)
        mainContainer.addView(toolbarRow2)

        // --- QWERTY Grid Container ---
        qwertyContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
""")

for row in keys:
    out.append("""
        val rowLayout{row_idx} = LinearLayout(this).apply {{
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            weightSum = 10f
        }}""".format(row_idx=keys.index(row)))
        
    if keys.index(row) == 2:
        out.append("""
        rowLayout{row_idx}.addView(View(this).apply {{ layoutParams = LinearLayout.LayoutParams(0, 1, 0.5f) }})""".format(row_idx=keys.index(row)))
        
    for key in row:
        if key == 'SHIFT':
            out.append("""
        rowLayout{row_idx}.addView(createKeyButton("⇧", isSpecial = true, weight = 1.5f) {{
            isShifted = !isShifted
            updateShiftState()
        }})""".format(row_idx=keys.index(row)))
        elif key == 'DEL':
            out.append("""
        rowLayout{row_idx}.addView(createBackspaceButton())""".format(row_idx=keys.index(row)))
        else:
            lp_val = long_press_map.get(key)
            sub_val = subscript_map.get(key, "")
            lp_code = f'currentInputConnection?.commitText("{lp_val}", 1)' if lp_val else ""
            out.append("""
        val btn_{key} = createKeyButton("{key}", isSpecial = false, subscript = "{sub_val}", longPressAction = {{ {lp_code} }}) {{
            val textToCommit = if (isShifted) "{key}".uppercase() else "{key}"
            currentInputConnection?.commitText(textToCommit, 1)
            if (isShifted) {{ isShifted = false; updateShiftState() }}
        }}
        rowLayout{row_idx}.addView(btn_{key})""".format(row_idx=keys.index(row), key=key, sub_val=sub_val, lp_code=lp_code))
        
    if keys.index(row) == 2:
        out.append("""
        rowLayout{row_idx}.addView(View(this).apply {{ layoutParams = LinearLayout.LayoutParams(0, 1, 0.5f) }})""".format(row_idx=keys.index(row)))
        
    out.append("        qwertyContainer.addView(rowLayout{row_idx})".format(row_idx=keys.index(row)))

out.append("""
        // --- Bottom Row ---
        val bottomRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            weightSum = 10f
        }
        
        val flowBtn = createHoldToTalkButton(1.5f)
        bottomRow.addView(flowBtn)
        
        bottomRow.addView(createKeyButton(",", isSpecial = true, weight = 1f) { currentInputConnection?.commitText(",", 1) })
        bottomRow.addView(createKeyButton("Space", isSpecial = false, weight = 5f) { currentInputConnection?.commitText(" ", 1) })
        bottomRow.addView(createKeyButton(".", isSpecial = true, weight = 1f) { currentInputConnection?.commitText(".", 1) })
        bottomRow.addView(createKeyButton("↵", isSpecial = true, weight = 1.5f) {
            currentInputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER))
            currentInputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_ENTER))
        })
        
        qwertyContainer.addView(bottomRow)
        mainContainer.addView(qwertyContainer)
        
        // --- Calculator Container ---
        calcContainer = createCalculatorView()
        mainContainer.addView(calcContainer)
        
        // --- Navigation Bar Bottom Spacer (50dp) ---
        val navSpacer = View(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, (50 * density).toInt())
            setBackgroundColor(Color.parseColor("#0A0A0A"))
        }
        mainContainer.addView(navSpacer)

        return mainContainer
    }
    
    private fun createBackspaceButton(): RelativeLayout {
        val density = resources.displayMetrics.density
        return RelativeLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, (45 * density).toInt(), 1.5f).apply {
                setMargins((1 * density).toInt(), (2 * density).toInt(), (1 * density).toInt(), (2 * density).toInt())
            }
            background = GradientDrawable().apply { setColor(Color.parseColor("#1A1A1A")); cornerRadius = 8f * density }
            isClickable = true
            isFocusable = true
            
            val mainText = TextView(this@FlowDictationIME).apply {
                text = "⌫"
                setTextColor(Color.WHITE)
                textSize = 20f
                gravity = Gravity.CENTER
                layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            }
            addView(mainText)
            
            val handler = Handler(Looper.getMainLooper())
            var isHolding = false
            var duration = 0L
            val runnable = object : Runnable {
                override fun run() {
                    if (!isHolding) return
                    duration += 100
                    if (duration > 500) {
                        val textBeforeCursor = currentInputConnection?.getTextBeforeCursor(50, 0)
                        if (textBeforeCursor.isNullOrEmpty()) {
                            currentInputConnection?.deleteSurroundingText(1, 0)
                        } else {
                            val lastSpace = textBeforeCursor.trimEnd().lastIndexOf(' ')
                            val deleteCount = if (lastSpace == -1) textBeforeCursor.length else textBeforeCursor.length - lastSpace
                            currentInputConnection?.deleteSurroundingText(deleteCount, 0)
                        }
                    } else {
                        currentInputConnection?.deleteSurroundingText(1, 0)
                    }
                    handler.postDelayed(this, 100)
                }
            }
            
            setOnTouchListener { v, event ->
                when(event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#444444")); cornerRadius = 8f * density }
                        
                        val ic = currentInputConnection
                        val text = ic?.getExtractedText(ExtractedTextRequest(), 0)
                        if (text != null && text.selectionStart != text.selectionEnd) {
                            ic.commitText("", 1)
                        } else {
                            isHolding = true
                            duration = 0L
                            handler.post(runnable)
                        }
                        true
                    }
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#1A1A1A")); cornerRadius = 8f * density }
                        isHolding = false
                        handler.removeCallbacks(runnable)
                        true
                    }
                    else -> false
                }
            }
        }
    }

    private fun createToolbarButton(textStr: String, bgColor: String, textColor: String, weight: Float, onClick: () -> Unit): TextView {
        val density = resources.displayMetrics.density
        return TextView(this).apply {
            text = textStr
            setTextColor(Color.parseColor(textColor))
            isAllCaps = false
            textSize = 12f
            gravity = Gravity.CENTER
            
            background = GradientDrawable().apply {
                setColor(Color.parseColor(bgColor))
                cornerRadius = 12f * density
            }
            
            layoutParams = LinearLayout.LayoutParams(0, (38 * density).toInt(), weight).apply {
                setMargins((1 * density).toInt(), (1 * density).toInt(), (1 * density).toInt(), (1 * density).toInt())
            }
            
            setOnTouchListener { v, event ->
                if (event.action == MotionEvent.ACTION_DOWN) v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                false
            }
            setOnClickListener { onClick() }
        }
    }

    private fun createKeyButton(textStr: String, isSpecial: Boolean, weight: Float = 1f, subscript: String = "", longPressAction: (() -> Unit)? = null, onClick: () -> Unit): RelativeLayout {
        val density = resources.displayMetrics.density
        val defaultColor = if (isSpecial) "#1A1A1A" else "#222222"
        val pressedColor = "#444444"
        
        return RelativeLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, (45 * density).toInt(), weight).apply {
                setMargins((1 * density).toInt(), (2 * density).toInt(), (1 * density).toInt(), (2 * density).toInt())
            }
            background = GradientDrawable().apply { setColor(Color.parseColor(defaultColor)); cornerRadius = 8f * density }
            isClickable = true
            isFocusable = true
            
            val mainText = TextView(this@FlowDictationIME).apply {
                text = textStr
                setTextColor(Color.WHITE)
                textSize = 20f
                gravity = Gravity.CENTER
                layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            }
            if (!isSpecial) keyViews.add(mainText)
            addView(mainText)
            
            if (subscript.isNotEmpty()) {
                val subText = TextView(this@FlowDictationIME).apply {
                    text = subscript
                    setTextColor(Color.parseColor("#888888"))
                    textSize = 10f
                    layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                        addRule(RelativeLayout.ALIGN_PARENT_TOP)
                        addRule(RelativeLayout.ALIGN_PARENT_RIGHT)
                        setMargins(0, (2 * density).toInt(), (4 * density).toInt(), 0)
                    }
                }
                addView(subText)
            }
            
            setOnTouchListener { v, event ->
                when(event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        v.background = GradientDrawable().apply { setColor(Color.parseColor(pressedColor)); cornerRadius = 8f * density }
                    }
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                        v.background = GradientDrawable().apply { setColor(Color.parseColor(defaultColor)); cornerRadius = 8f * density }
                    }
                }
                false
            }
            
            if (longPressAction != null) {
                setOnLongClickListener {
                    it.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                    longPressAction()
                    true
                }
            }
            setOnClickListener { onClick() }
        }
    }
    
    private fun createHoldToTalkButton(weight: Float): RelativeLayout {
        val density = resources.displayMetrics.density
        return RelativeLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, (45 * density).toInt(), weight).apply {
                setMargins((1 * density).toInt(), (2 * density).toInt(), (1 * density).toInt(), (2 * density).toInt())
            }
            background = GradientDrawable().apply { setColor(Color.parseColor("#4A90E2")); cornerRadius = 8f * density }
            isClickable = true
            isFocusable = true
            
            val mainText = TextView(this@FlowDictationIME).apply {
                text = "🎤"
                setTextColor(Color.WHITE)
                textSize = 20f
                gravity = Gravity.CENTER
                layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            }
            addView(mainText)
            
            val holdHandler = Handler(Looper.getMainLooper())
            var isHolding = false
            
            val holdRunnable = Runnable {
                if (!isHolding) return@Runnable
                // CRITICAL FIX: Set the system-wide recording boolean so the thread doesn't exit!
                isRecording = true
                updateUI()
                performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                try { startAudioCapture() } catch (e: Exception) { Log.e("Flow", "Mic failed", e) }
            }
            
            setOnTouchListener { v, event ->
                when(event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        v.parent?.requestDisallowInterceptTouchEvent(true)
                        v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#E24A4A")); cornerRadius = 8f * density }
                        isHolding = true
                        holdHandler.postDelayed(holdRunnable, 100) // Fast trigger
                        true
                    }
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                        v.parent?.requestDisallowInterceptTouchEvent(false)
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#4A90E2")); cornerRadius = 8f * density }
                        
                        if (isHolding) {
                            holdHandler.removeCallbacks(holdRunnable)
                            isHolding = false
                            if (isRecording) {
                                isRecording = false
                                updateUI()
                                try { stopAudioCaptureAndProcess() } catch (e: Exception) { Log.e("Flow", "Mic failed", e) }
                            }
                        }
                        true
                    }
                    else -> false
                }
            }
        }
    }
    
    private fun createCalculatorView(): LinearLayout {
        val density = resources.displayMetrics.density
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            visibility = View.GONE
            
            calcDisplay = TextView(this@FlowDictationIME).apply {
                text = "0"
                setTextColor(Color.WHITE)
                textSize = 30f
                gravity = Gravity.END or Gravity.CENTER_VERTICAL
                setPadding((10 * density).toInt(), (10 * density).toInt(), (10 * density).toInt(), (10 * density).toInt())
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, (60 * density).toInt())
                background = GradientDrawable().apply { setColor(Color.parseColor("#111111")); cornerRadius = 8f * density }
            }
            addView(calcDisplay)
            
            val calcKeys = listOf(
                listOf("7", "8", "9", "÷"),
                listOf("4", "5", "6", "×"),
                listOf("1", "2", "3", "-"),
                listOf("C", "0", "=", "+")
            )
            
            for (row in calcKeys) {
                val rowLayout = LinearLayout(this@FlowDictationIME).apply {
                    orientation = LinearLayout.HORIZONTAL
                    layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                    weightSum = 4f
                }
                for (key in row) {
                    rowLayout.addView(createKeyButton(key, isSpecial = (key == "C" || key == "=" || key in listOf("÷", "×", "-", "+")), weight = 1f) {
                        handleCalcInput(key)
                    })
                }
                addView(rowLayout)
            }
            
            val closeBtn = createKeyButton("Return to Keyboard", isSpecial = true, weight = 1f) {
                toggleCalculatorMode()
            }
            addView(closeBtn)
        }
    }
    
    private fun evalMath(str: String): Double {
        return object : Any() {
            var pos = -1
            var ch = 0
            fun nextChar() { ch = if (++pos < str.length) str[pos].code else -1 }
            fun eat(charToEat: Int): Boolean {
                while (ch == ' '.code) nextChar()
                if (ch == charToEat) { nextChar(); return true }
                return false
            }
            fun parse(): Double {
                nextChar()
                val x = parseExpression()
                if (pos < str.length) throw RuntimeException("Unexpected: " + ch.toChar())
                return x
            }
            fun parseExpression(): Double {
                var x = parseTerm()
                while (true) {
                    if (eat('+'.code)) x += parseTerm()
                    else if (eat('-'.code)) x -= parseTerm()
                    else return x
                }
            }
            fun parseTerm(): Double {
                var x = parseFactor()
                while (true) {
                    if (eat('×'.code) || eat('*'.code)) x *= parseFactor()
                    else if (eat('÷'.code) || eat('/'.code)) x /= parseFactor()
                    else return x
                }
            }
            fun parseFactor(): Double {
                if (eat('+'.code)) return parseFactor()
                if (eat('-'.code)) return -parseFactor()
                var x: Double
                val startPos = this.pos
                if ((ch >= '0'.code && ch <= '9'.code) || ch == '.'.code) {
                    while ((ch >= '0'.code && ch <= '9'.code) || ch == '.'.code) nextChar()
                    x = str.substring(startPos, this.pos).toDouble()
                } else {
                    throw RuntimeException("Unexpected: " + ch.toChar())
                }
                return x
            }
        }.parse()
    }
    
    private fun handleCalcInput(input: String) {
        if (input == "C") { currentCalcText = "0" }
        else if (input == "=") {
            try {
                val result = evalMath(currentCalcText)
                val resultStr = if (result == result.toLong().toDouble()) result.toLong().toString() else result.toString()
                currentInputConnection?.commitText(resultStr, 1)
                currentCalcText = "0"
                toggleCalculatorMode()
            } catch (e: Exception) { currentCalcText = "Err" }
        } else {
            if (currentCalcText == "0" && input !in listOf("÷", "×", "-", "+")) currentCalcText = input
            else currentCalcText += input
        }
        calcDisplay.text = currentCalcText
    }
    
    private fun toggleCalculatorMode() {
        if (qwertyContainer.visibility == View.VISIBLE) {
            qwertyContainer.visibility = View.GONE
            calcContainer.visibility = View.VISIBLE
            currentCalcText = "0"
            calcDisplay.text = currentCalcText
        } else {
            qwertyContainer.visibility = View.VISIBLE
            calcContainer.visibility = View.GONE
        }
    }

    private fun updateShiftState() {
        keyViews.forEach { tv ->
            val currentText = tv.text.toString()
            if (currentText.length == 1 && currentText[0].isLetter()) {
                tv.text = if (isShifted) currentText.uppercase() else currentText.lowercase()
            }
        }
    }

    private fun rewriteText() {
        coroutineScope.launch {
            val ic = currentInputConnection
            val text = ic?.getExtractedText(ExtractedTextRequest(), 0)?.text?.toString()
            if (text.isNullOrBlank()) return@launch
            val prompt = "Rewrite and professionalize this text. Output only the final text, no quotes or intro: $text"
            val newText = formatWithGemini(prompt, "gemini-3.5-flash")
            withContext(Dispatchers.Main) {
                ic.deleteSurroundingText(10000, 10000)
                ic.commitText(newText, 1)
            }
        }
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        isRecording = false
        isShifted = false
        updateShiftState()
        updateUI()
    }

    override fun onDestroy() {
        super.onDestroy()
        serviceJob.cancel()
        audioRecord?.release()
    }

    private fun updateUI() {
        if (isRecording) {
            dictationButton.setTextColor(Color.parseColor("#FF4444"))
            if (recordingAnimator == null) {
                recordingAnimator = ObjectAnimator.ofFloat(dictationButton, "alpha", 1f, 0.3f).apply {
                    duration = 600
                    repeatCount = ObjectAnimator.INFINITE
                    repeatMode = ObjectAnimator.REVERSE
                    start()
                }
            } else {
                recordingAnimator?.start()
            }
        } else {
            recordingAnimator?.cancel()
            dictationButton.alpha = 1f
            dictationButton.setTextColor(Color.WHITE)
        }
    }

    private fun toggleDictation() {
        isRecording = !isRecording
        updateUI()
        if (isRecording) {
            try { startAudioCapture() } catch (e: Exception) { Log.e("Flow", "Mic failed", e) }
        } else {
            try { stopAudioCaptureAndProcess() } catch (e: Exception) { Log.e("Flow", "Mic failed", e) }
        }
    }

    private fun startAudioCapture() {
        audioBuffer.reset()
        audioRecord = AudioRecord(MediaRecorder.AudioSource.MIC, sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, bufferSize)
        audioRecord?.startRecording()
        recordingThread = Thread {
            val data = ByteArray(bufferSize)
            while (isRecording) {
                val read = audioRecord?.read(data, 0, data.size) ?: 0
                if (read > 0) audioBuffer.write(data, 0, read)
            }
        }.apply { start() }
    }

    private fun stopAudioCaptureAndProcess() {
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
        
        val pcmData = audioBuffer.toByteArray()
        if (pcmData.isEmpty()) return
        val wavData = createWavData(pcmData, sampleRate, 1)

        coroutineScope.launch {
            try {
                // Step 1: Lightning fast transcription
                val transcript = transcribeWithGroq(wavData)
                if (transcript.isNullOrBlank()) return@launch

                // Step 2: Instant Groq Llama-3 Formatting
                val smartText = formatWithGroqLLM(transcript)

                withContext(Dispatchers.Main) {
                    currentInputConnection?.commitText(smartText + " ", 1)
                }
            } catch (e: Exception) { Log.e("FlowDictation", "Error", e) }
        }
    }

    private fun createWavData(pcmData: ByteArray, sampleRate: Int, channels: Int): ByteArray {
        val totalDataLen = pcmData.size + 36
        val byteRate = sampleRate * channels * 2
        val header = ByteBuffer.allocate(44).apply {
            order(ByteOrder.LITTLE_ENDIAN)
            put("RIFF".toByteArray()); putInt(totalDataLen); put("WAVE".toByteArray())
            put("fmt ".toByteArray()); putInt(16); putShort(1); putShort(channels.toShort())
            putInt(sampleRate); putInt(byteRate); putShort((channels * 2).toShort()); putShort(16)
            put("data".toByteArray()); putInt(pcmData.size)
        }.array()
        return header + pcmData
    }

    private suspend fun transcribeWithGroq(audioData: ByteArray): String? = withContext(Dispatchers.IO) {
        val client = OkHttpClient()
        val requestBody = MultipartBody.Builder().setType(MultipartBody.FORM).addFormDataPart("file", "audio.wav", audioData.toRequestBody("audio/wav".toMediaType())).addFormDataPart("model", "whisper-large-v3").addFormDataPart("response_format", "json").build()
        val request = Request.Builder().url("https://api.groq.com/openai/v1/audio/transcriptions").addHeader("Authorization", "Bearer $groqApiKey").post(requestBody).build()
        val response = client.newCall(request).execute()
        val bodyStr = response.body?.string()
        if (response.isSuccessful && bodyStr != null) return@withContext JSONObject(bodyStr).optString("text")
        return@withContext null
    }

    private suspend fun formatWithGroqLLM(text: String): String = withContext(Dispatchers.IO) {
        val client = OkHttpClient()
        val json = JSONObject().apply {
            put("model", "llama3-8b-8192")
            put("messages", JSONArray().apply {
                put(JSONObject().apply {
                    put("role", "system")
                    put("content", "You are an expert dictation formatter. Output ONLY the clean, grammatically corrected text. No filler, no intro, no quotes.")
                })
                put(JSONObject().apply {
                    put("role", "user")
                    put("content", text)
                })
            })
            put("temperature", 0.0)
        }
        val requestBody = json.toString().toRequestBody("application/json".toMediaType())
        val request = Request.Builder().url("https://api.groq.com/openai/v1/chat/completions").addHeader("Authorization", "Bearer $groqApiKey").post(requestBody).build()
        val response = client.newCall(request).execute()
        val bodyStr = response.body?.string()
        if (response.isSuccessful && bodyStr != null) {
            val jsonResponse = JSONObject(bodyStr)
            val choices = jsonResponse.optJSONArray("choices")
            if (choices != null && choices.length() > 0) {
                return@withContext choices.getJSONObject(0).optJSONObject("message")?.optString("content")?.trim() ?: text
            }
        }
        return@withContext text
    }

    private suspend fun formatWithGemini(prompt: String, model: String): String = withContext(Dispatchers.IO) {
        val generativeModel = GenerativeModel(modelName = model, apiKey = geminiApiKey, systemInstruction = content { text("Output only formatted text. No filler.") })
        return@withContext generativeModel.generateContent(prompt).text?.trim() ?: ""
    }
}
""")

with open(r"C:\Users\z_tes\.gemini\antigravity\scratch\flow-dictation\android-client\app\src\main\java\com\example\flowdictation\FlowDictationIME.kt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("V7 Kotlin file generated successfully!")
