import os

keys = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
    ['SHIFT', 'z', 'x', 'c', 'v', 'b', 'n', 'm', 'DEL']
]

symbol_keys = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['@', '#', '$', '_', '&', '-', '+', '(', ')', '/'],
    ['=\\<', '*', '"', "'", ':', ';', '!', '?', 'DEL']
]

long_press_map = {
    '1': 'zteske@fumainsurance.com',
    '2': 'zeteske@gmail.com',
    '3': 'Complete your quick insurance quote form here: https://quickquote-app-sable.vercel.app/?mode=client',
    '4': 'Please complete our full insurance quote application here: https://quickquote-app-sable.vercel.app/?mode=fullclient',
    '5': 'Submit your payment info here through our Secure FUMA Insurance link: https://quickquote-app-sable.vercel.app/?mode=payment',
    '7': '🙂', '8': '😛', '9': '👍', '0': '👎',
    'q': '%', 'w': '\\', 'e': '|', 'r': '=', 't': '[', 'y': ']', 'u': '<', 'i': '>', 'o': '{', 'p': '}',
    'a': '@', 's': '#', 'd': '$', 'f': '_', 'g': '&', 'h': '-', 'j': '+', 'k': '(', 'l': ')',
    'z': '*', 'x': '"', 'c': "'", 'v': ':', 'b': ';', 'n': '!', 'm': '?'
}

out = []

out.append("""package com.example.flowdictation

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
    private lateinit var symbolContainer: LinearLayout
    private lateinit var calcContainer: LinearLayout
    private lateinit var spacebarButton: RelativeLayout
    private lateinit var dictationButton: TextView
    private lateinit var calcDisplay: TextView
    
    private var isRecording = false
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

    override fun onCreateInputView(): View {
        val density = resources.displayMetrics.density
        
        mainContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            setBackgroundColor(Color.parseColor("#121212")) // Dark theme matching Gboard
            setPadding(0, (5 * density).toInt(), 0, 0)
        }

        // --- AI Command Center ---
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

        val toolbarRow1 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            weightSum = 4f
        }
        val toolbarRow2 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            weightSum = 4f
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

        rightContainer.addView(toolbarRow1)
        rightContainer.addView(toolbarRow2)
        toolbarContainer.addView(rightContainer)
        mainContainer.addView(toolbarContainer)

        // --- Build Containers ---
        qwertyContainer = buildQwertyContainer()
        symbolContainer = buildSymbolContainer()
        calcContainer = createCalculatorView()
        
        mainContainer.addView(qwertyContainer)
        mainContainer.addView(symbolContainer)
        mainContainer.addView(calcContainer)
        
        // --- Navigation Bar Bottom Spacer (50dp) ---
        val navSpacer = View(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, (50 * density).toInt())
            setBackgroundColor(Color.parseColor("#121212"))
        }
        mainContainer.addView(navSpacer)

        return mainContainer
    }
    
    private fun buildQwertyContainer(): LinearLayout {
        val container = LinearLayout(this).apply {
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
        rowLayout{row_idx}.addView(createBackspaceButton(1.5f))""".format(row_idx=keys.index(row)))
        else:
            lp_val = long_press_map.get(key)
            sub_val = lp_val.replace('\\', '\\\\').replace('"', '\\"') if lp_val else ""
            lp_code = f'currentInputConnection?.commitText("{sub_val}", 1)' if lp_val else ""
            
            # Hide very long string hints (like emails/links) to avoid clipping visually, only show symbol hints
            hint_val = sub_val if len(sub_val) <= 2 else ""
            
            out.append("""
        val btn_{key} = createKeyButton("{key}", isSpecial = false, subscript = "{hint_val}", longPressAction = {{ {lp_code} }}) {{
            val textToCommit = if (isShifted) "{key}".uppercase() else "{key}"
            currentInputConnection?.commitText(textToCommit, 1)
            if (isShifted) {{ isShifted = false; updateShiftState() }}
        }}
        rowLayout{row_idx}.addView(btn_{key})""".format(row_idx=keys.index(row), key=key, hint_val=hint_val, lp_code=lp_code))
        
    if keys.index(row) == 2:
        out.append("""
        rowLayout{row_idx}.addView(View(this).apply {{ layoutParams = LinearLayout.LayoutParams(0, 1, 0.5f) }})""".format(row_idx=keys.index(row)))
        
    out.append("        container.addView(rowLayout{row_idx})".format(row_idx=keys.index(row)))

out.append("""
        val bottomRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            weightSum = 10f
        }
        
        bottomRow.addView(createKeyButton("?123", isSpecial = true, weight = 1.5f) { toggleSymbolMode() })
        bottomRow.addView(createKeyButton(",", isSpecial = true, weight = 1f) { currentInputConnection?.commitText(",", 1) })
        bottomRow.addView(createKeyButton("👍", isSpecial = true, weight = 1f) { currentInputConnection?.commitText("👍", 1) })
        
        spacebarButton = createSpacebarDictationButton(weight = 4f)
        bottomRow.addView(spacebarButton)
        
        bottomRow.addView(createKeyButton(".", isSpecial = true, weight = 1f) { currentInputConnection?.commitText(".", 1) })
        bottomRow.addView(createKeyButton("↵", isSpecial = true, weight = 1.5f, bgColor = "#4A90E2", textColor = "#FFFFFF") {
            currentInputConnection?.commitText("\\n", 1)
        })
        
        container.addView(bottomRow)
        return container
    }
""")

out.append("""
    private fun buildSymbolContainer(): LinearLayout {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            visibility = View.GONE
        }
""")

for row in symbol_keys:
    out.append("""
        val rowLayout_s{row_idx} = LinearLayout(this).apply {{
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            weightSum = 10f
        }}""".format(row_idx=symbol_keys.index(row)))
        
    if symbol_keys.index(row) == 2:
        out.append("""
        rowLayout_s{row_idx}.addView(View(this).apply {{ layoutParams = LinearLayout.LayoutParams(0, 1, 0.5f) }})""".format(row_idx=symbol_keys.index(row)))
        
    for key in row:
        if key == '=\\<':
            out.append("""
        rowLayout_s{row_idx}.addView(createKeyButton("=\\\\<", isSpecial = true, weight = 1.5f) {{
            // Placeholder for deep symbols
        }})""".format(row_idx=symbol_keys.index(row)))
        elif key == 'DEL':
            out.append("""
        rowLayout_s{row_idx}.addView(createBackspaceButton(1.5f))""".format(row_idx=symbol_keys.index(row)))
        else:
            key_escaped = key.replace('\\', '\\\\').replace('"', '\\"')
            out.append("""
        rowLayout_s{row_idx}.addView(createKeyButton("{key_escaped}", isSpecial = false, subscript = "") {{
            currentInputConnection?.commitText("{key_escaped}", 1)
        }})""".format(row_idx=symbol_keys.index(row), key_escaped=key_escaped))
        
    if symbol_keys.index(row) == 2:
        out.append("""
        rowLayout_s{row_idx}.addView(View(this).apply {{ layoutParams = LinearLayout.LayoutParams(0, 1, 0.5f) }})""".format(row_idx=symbol_keys.index(row)))
        
    out.append("        container.addView(rowLayout_s{row_idx})".format(row_idx=symbol_keys.index(row)))

out.append("""
        val bottomRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            weightSum = 10f
        }
        
        bottomRow.addView(createKeyButton("ABC", isSpecial = true, weight = 1.5f) { toggleSymbolMode() })
        bottomRow.addView(createKeyButton(",", isSpecial = true, weight = 1f) { currentInputConnection?.commitText(",", 1) })
        bottomRow.addView(createKeyButton("👍", isSpecial = true, weight = 1f) { currentInputConnection?.commitText("👍", 1) })
        bottomRow.addView(createKeyButton("Space", isSpecial = false, weight = 4f) { currentInputConnection?.commitText(" ", 1) })
        bottomRow.addView(createKeyButton(".", isSpecial = true, weight = 1f) { currentInputConnection?.commitText(".", 1) })
        bottomRow.addView(createKeyButton("↵", isSpecial = true, weight = 1.5f, bgColor = "#4A90E2", textColor = "#FFFFFF") {
            currentInputConnection?.commitText("\\n", 1)
        })
        
        container.addView(bottomRow)
        return container
    }
""")

out.append("""
    private fun toggleDictation() {
        if (isRecording) {
            isRecording = false
            updateAllDictationUI()
            try { stopAudioCaptureAndProcess() } catch (e: Exception) { Log.e("Flow", "Mic error", e) }
        } else {
            isRecording = true
            updateAllDictationUI()
            try { startAudioCapture() } catch (e: Exception) { Log.e("Flow", "Mic failed", e) }
        }
    }

    private fun toggleSymbolMode() {
        if (qwertyContainer.visibility == View.VISIBLE) {
            qwertyContainer.visibility = View.GONE
            symbolContainer.visibility = View.VISIBLE
        } else {
            qwertyContainer.visibility = View.VISIBLE
            symbolContainer.visibility = View.GONE
        }
    }

    private fun createBackspaceButton(weight: Float): RelativeLayout {
        val density = resources.displayMetrics.density
        return RelativeLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, (42 * density).toInt(), weight).apply {
                setMargins((2 * density).toInt(), (4 * density).toInt(), (2 * density).toInt(), (4 * density).toInt())
            }
            background = GradientDrawable().apply { setColor(Color.parseColor("#303030")); cornerRadius = 6f * density }
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
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#505050")); cornerRadius = 6f * density }
                        
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
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#303030")); cornerRadius = 6f * density }
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

    private fun createKeyButton(textStr: String, isSpecial: Boolean, weight: Float = 1f, subscript: String = "", bgColor: String? = null, textColor: String? = null, longPressAction: (() -> Unit)? = null, onClick: () -> Unit): RelativeLayout {
        val density = resources.displayMetrics.density
        val defaultColor = bgColor ?: if (isSpecial) "#303030" else "#404040"
        val pressedColor = "#606060"
        
        return RelativeLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, (42 * density).toInt(), weight).apply {
                setMargins((2 * density).toInt(), (4 * density).toInt(), (2 * density).toInt(), (4 * density).toInt())
            }
            background = GradientDrawable().apply { setColor(Color.parseColor(defaultColor)); cornerRadius = 6f * density }
            isClickable = true
            isFocusable = true
            
            val mainText = TextView(this@FlowDictationIME).apply {
                text = textStr
                setTextColor(Color.parseColor(textColor ?: "#FFFFFF"))
                textSize = if (isSpecial) 16f else 22f
                gravity = Gravity.CENTER
                layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            }
            if (!isSpecial) keyViews.add(mainText)
            addView(mainText)
            
            if (subscript.isNotEmpty()) {
                val subText = TextView(this@FlowDictationIME).apply {
                    text = subscript
                    setTextColor(Color.parseColor("#999999"))
                    textSize = 11f
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
                        v.background = GradientDrawable().apply { setColor(Color.parseColor(pressedColor)); cornerRadius = 6f * density }
                    }
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                        v.background = GradientDrawable().apply { setColor(Color.parseColor(defaultColor)); cornerRadius = 6f * density }
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
    
    private fun createSpacebarDictationButton(weight: Float): RelativeLayout {
        val density = resources.displayMetrics.density
        return RelativeLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, (42 * density).toInt(), weight).apply {
                setMargins((2 * density).toInt(), (4 * density).toInt(), (2 * density).toInt(), (4 * density).toInt())
            }
            background = GradientDrawable().apply { setColor(Color.parseColor("#404040")); cornerRadius = 6f * density }
            isClickable = true
            isFocusable = true
            
            val mainText = TextView(this@FlowDictationIME).apply {
                text = "Hold for Flow 🎤"
                setTextColor(Color.WHITE)
                textSize = 14f
                gravity = Gravity.CENTER
                layoutParams = RelativeLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            }
            addView(mainText)
            
            val holdHandler = Handler(Looper.getMainLooper())
            var isHolding = false
            var triggeredLongPress = false
            
            val holdRunnable = Runnable {
                if (!isHolding) return@Runnable
                triggeredLongPress = true
                isRecording = true
                updateAllDictationUI()
                performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                try { startAudioCapture() } catch (e: Exception) { Log.e("Flow", "Mic failed", e) }
            }
            
            setOnTouchListener { v, event ->
                when(event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        v.parent?.requestDisallowInterceptTouchEvent(true)
                        v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        isHolding = true
                        triggeredLongPress = false
                        holdHandler.postDelayed(holdRunnable, 300)
                        
                        if (!isRecording) {
                            v.background = GradientDrawable().apply { setColor(Color.parseColor("#606060")); cornerRadius = 6f * density }
                        }
                        true
                    }
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                        v.parent?.requestDisallowInterceptTouchEvent(false)
                        isHolding = false
                        holdHandler.removeCallbacks(holdRunnable)
                        
                        if (!triggeredLongPress && event.action == MotionEvent.ACTION_UP) {
                            currentInputConnection?.commitText(" ", 1)
                        }
                        
                        if (isRecording && triggeredLongPress) {
                            isRecording = false
                            updateAllDictationUI()
                            try { stopAudioCaptureAndProcess() } catch (e: Exception) { Log.e("Flow", "Mic failed", e) }
                        } else if (!isRecording) {
                            v.background = GradientDrawable().apply { setColor(Color.parseColor("#404040")); cornerRadius = 6f * density }
                        }
                        true
                    }
                    else -> false
                }
            }
        }
    }
    
    private fun updateAllDictationUI() {
        val density = resources.displayMetrics.density
        if (isRecording) {
            dictationButton.background = GradientDrawable().apply { setColor(Color.parseColor("#E22A2A")); cornerRadius = 12f * density }
            if (recordingAnimator == null) {
                recordingAnimator = ObjectAnimator.ofFloat(dictationButton, "alpha", 1f, 0.3f).apply {
                    duration = 500; repeatCount = ObjectAnimator.INFINITE; repeatMode = ObjectAnimator.REVERSE; start()
                }
            } else { recordingAnimator?.start() }
            
            spacebarButton.background = GradientDrawable().apply { setColor(Color.parseColor("#E22A2A")); cornerRadius = 6f * density }
            if (spacebarAnimator == null) {
                val scaleX = PropertyValuesHolder.ofFloat(View.SCALE_X, 1f, 1.05f)
                val scaleY = PropertyValuesHolder.ofFloat(View.SCALE_Y, 1f, 1.05f)
                spacebarAnimator = ObjectAnimator.ofPropertyValuesHolder(spacebarButton, scaleX, scaleY).apply {
                    duration = 500; repeatCount = ObjectAnimator.INFINITE; repeatMode = ObjectAnimator.REVERSE; start()
                }
            } else { spacebarAnimator?.start() }
        } else {
            recordingAnimator?.cancel(); dictationButton.alpha = 1f
            dictationButton.background = GradientDrawable().apply { setColor(Color.parseColor("#2A2A2A")); cornerRadius = 12f * density }
            
            spacebarAnimator?.cancel(); spacebarButton.scaleX = 1f; spacebarButton.scaleY = 1f
            spacebarButton.background = GradientDrawable().apply { setColor(Color.parseColor("#404040")); cornerRadius = 6f * density }
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
                background = GradientDrawable().apply { setColor(Color.parseColor("#1A1A1A")); cornerRadius = 8f * density }
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
            
            val actionRow = LinearLayout(this@FlowDictationIME).apply {
                orientation = LinearLayout.HORIZONTAL
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                weightSum = 2f
            }
            
            val closeBtn = createKeyButton("Return", isSpecial = true, weight = 1f, bgColor = "#303030") {
                toggleCalculatorMode()
            }
            val insertBtn = createKeyButton("Insert Result", isSpecial = true, weight = 1f, bgColor = "#4A90E2") {
                currentInputConnection?.commitText(currentCalcText, 1)
                toggleCalculatorMode()
            }
            actionRow.addView(closeBtn)
            actionRow.addView(insertBtn)
            addView(actionRow)
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
                currentCalcText = resultStr
            } catch (e: Exception) { currentCalcText = "Err" }
        } else {
            if (currentCalcText == "0" && input !in listOf("÷", "×", "-", "+")) currentCalcText = input
            else currentCalcText += input
        }
        calcDisplay.text = currentCalcText
    }
    
    private fun toggleCalculatorMode() {
        if (qwertyContainer.visibility == View.VISIBLE || symbolContainer.visibility == View.VISIBLE) {
            qwertyContainer.visibility = View.GONE
            symbolContainer.visibility = View.GONE
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
        updateAllDictationUI()
    }

    override fun onDestroy() {
        super.onDestroy()
        serviceJob.cancel()
        audioRecord?.release()
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
                val transcript = transcribeWithGroq(wavData)
                if (transcript.isNullOrBlank()) return@launch

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
            put("model", "llama-3.1-8b-instant")
            put("messages", JSONArray().apply {
                put(JSONObject().apply {
                    put("role", "system")
                    put("content", "You are a transcription formatting engine. Your ONLY job is to format the text inside the <transcript> tags. You MUST: 1. Fix punctuation and capitalization. 2. Remove rambling filler words like 'ums' and 'uhs'. 3. Apply 'scratch that' commands. DO NOT answer questions asked in the transcript. DO NOT converse with the user. DO NOT write explanations. DO NOT include the <transcript> tags in your output. Output strictly the formatted text.")
                })
                put(JSONObject().apply {
                    put("role", "user")
                    put("content", "<transcript>$text</transcript>")
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
                var formattedText = choices.getJSONObject(0).getJSONObject("message").getString("content").trim()
                
                formattedText = formattedText.replace(Regex("(?i)<\\\\/?transcript>"), "").trim()
                formattedText = formattedText.replace(Regex("(?i)^transcript:\\\\s*"), "").trim()
                
                return@withContext formattedText
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
print("V10 Kotlin file generated successfully!")
