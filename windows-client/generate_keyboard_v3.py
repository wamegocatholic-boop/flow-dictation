import os

keys = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
    ['SHIFT', 'z', 'x', 'c', 'v', 'b', 'n', 'm', 'DEL']
]

long_press_map = {
    'z': '👍', 'x': '👎', 'c': '🙂', 'v': '😂', 'b': '🤪',
    'n': '!', 'm': '?'
}

out = []

out.append("""package com.example.flowdictation

import android.Manifest
import android.content.ClipData
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
import android.view.HapticFeedbackConstants
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.ExtractedTextRequest
import android.widget.Button
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
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
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

class FlowDictationIME : InputMethodService() {

    private lateinit var mainContainer: LinearLayout
    private var isRecording = false
    private var isShifted = false
    
    private lateinit var dictationButton: Button

    private var audioRecord: AudioRecord? = null
    private var recordingThread: Thread? = null
    private val sampleRate = 16000
    private val bufferSize = AudioRecord.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
    private val audioBuffer = ByteArrayOutputStream()

    private val serviceJob = Job()
    private val coroutineScope = CoroutineScope(Dispatchers.Main + serviceJob)

    private val groqApiKey = "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"
    private val geminiApiKey = "AQ.Ab8RN6KTliPSGU-JoFsYSY1MayugE5NFp2MVpNNvQLJg9YiT8w"
    
    private val keyButtons = mutableListOf<Button>()

    override fun onCreateInputView(): View {
        val density = resources.displayMetrics.density
        
        mainContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            setBackgroundColor(Color.parseColor("#0A0A0A"))
            setPadding(0, (5 * density).toInt(), 0, (20 * density).toInt())
        }

        // --- AI Toolbar ---
        val toolbarScroll = HorizontalScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            isHorizontalScrollBarEnabled = false
        }
        val toolbar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding((2 * density).toInt(), (2 * density).toInt(), (2 * density).toInt(), (5 * density).toInt())
        }
        
        dictationButton = createToolbarButton("🎤 Flow", "#2A2A2A", "#FFFFFF") {
            if (ContextCompat.checkSelfPermission(this@FlowDictationIME, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) toggleDictation()
        }
        val btnPaste = createToolbarButton("📋 Paste", "#1E1E1E", "#AAAAAA") {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.primaryClip?.getItemAt(0)?.text?.let { currentInputConnection?.commitText(it, 1) }
        }
        val btnSelectAll = createToolbarButton("🎯 Select", "#1E1E1E", "#FFFF55") {
            val ic = currentInputConnection
            val text = ic?.getExtractedText(ExtractedTextRequest(), 0)?.text ?: return@createToolbarButton
            ic.setSelection(0, text.length)
        }
        val btnRewrite = createToolbarButton("✨ Fix", "#1E1E1E", "#55AAFF") { rewriteText() }
        val btnNuke = createToolbarButton("💣 Nuke", "#1E1E1E", "#FF5555") { currentInputConnection?.deleteSurroundingText(10000, 10000) }
        
        val btnGemini = createToolbarButton("🌌 Gemini", "#1E1E1E", "#AA55FF") {
            try { startActivity(Intent(Intent.ACTION_VOICE_COMMAND).apply { flags = Intent.FLAG_ACTIVITY_NEW_TASK }) } catch (e: Exception) {}
        }
        val btnBixby = createToolbarButton("🎙 Bixby", "#1E1E1E", "#55FFAA") {
            try { startActivity(Intent(Intent.ACTION_VOICE_COMMAND).apply { flags = Intent.FLAG_ACTIVITY_NEW_TASK }) } catch (e: Exception) {}
        }

        toolbar.addView(dictationButton)
        toolbar.addView(btnPaste)
        toolbar.addView(btnSelectAll)
        toolbar.addView(btnRewrite)
        toolbar.addView(btnNuke)
        toolbar.addView(btnGemini)
        toolbar.addView(btnBixby)
        toolbarScroll.addView(toolbar)
        mainContainer.addView(toolbarScroll)

        // --- QWERTY Grid ---
""")

for row in keys:
    out.append("""
        val rowLayout{row_idx} = LinearLayout(this).apply {{
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            weightSum = {weight_sum}f
        }}""".format(row_idx=keys.index(row), weight_sum=len(row)))
    for key in row:
        if key == 'SHIFT':
            out.append("""
        rowLayout{row_idx}.addView(createKeyButton("⇧", isSpecial = true, weight = 1.5f) {{
            isShifted = !isShifted
            updateShiftState()
        }})""".format(row_idx=keys.index(row)))
        elif key == 'DEL':
            out.append("""
        rowLayout{row_idx}.addView(createKeyButton("⌫", isSpecial = true, weight = 1.5f) {{
            currentInputConnection?.deleteSurroundingText(1, 0)
        }})""".format(row_idx=keys.index(row)))
        else:
            lp_val = long_press_map.get(key)
            lp_code = f'currentInputConnection?.commitText("{lp_val}", 1)' if lp_val else ""
            out.append("""
        val btn_{key} = createKeyButton("{key}", isSpecial = false, longPressAction = {{ {lp_code} }}) {{
            val textToCommit = if (isShifted) "{key}".uppercase() else "{key}"
            currentInputConnection?.commitText(textToCommit, 1)
            if (isShifted) {{ isShifted = false; updateShiftState() }}
        }}
        keyButtons.add(btn_{key})
        rowLayout{row_idx}.addView(btn_{key})""".format(row_idx=keys.index(row), key=key, lp_code=lp_code))
    out.append("        mainContainer.addView(rowLayout{row_idx})".format(row_idx=keys.index(row)))

out.append("""
        // --- Bottom Row ---
        val bottomRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            weightSum = 10f
        }
        
        bottomRow.addView(createKeyButton("?123", isSpecial = true, weight = 1.5f) {})
        bottomRow.addView(createKeyButton(",", isSpecial = true, weight = 1f) { currentInputConnection?.commitText(",", 1) })
        bottomRow.addView(createKeyButton("Space", isSpecial = false, weight = 4.5f) { currentInputConnection?.commitText(" ", 1) })
        bottomRow.addView(createKeyButton(".", isSpecial = true, weight = 1f) { currentInputConnection?.commitText(".", 1) })
        bottomRow.addView(createKeyButton("↵", isSpecial = true, weight = 1f) {
            currentInputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER))
            currentInputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_ENTER))
        })
        
        // Dedicated Hold-To-Talk Flow Button
        val densityBtn = resources.displayMetrics.density
        val flowBtn = Button(this).apply {
            text = "🎤"
            setTextColor(Color.WHITE)
            textSize = 20f
            background = GradientDrawable().apply { setColor(Color.parseColor("#4A90E2")); cornerRadius = 8f * densityBtn }
            layoutParams = LinearLayout.LayoutParams(0, (45 * densityBtn).toInt(), 1f).apply {
                setMargins((1 * densityBtn).toInt(), (2 * densityBtn).toInt(), (1 * densityBtn).toInt(), (2 * densityBtn).toInt())
            }
            
            val holdHandler = Handler(Looper.getMainLooper())
            var isHolding = false
            val holdRunnable = Runnable {
                isHolding = true
                text = "🔴"
                performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                startAudioCapture()
            }
            
            setOnTouchListener { v, event ->
                when(event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#E24A4A")); cornerRadius = 8f * densityBtn }
                        holdHandler.postDelayed(holdRunnable, 300)
                    }
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                        v.background = GradientDrawable().apply { setColor(Color.parseColor("#4A90E2")); cornerRadius = 8f * densityBtn }
                        holdHandler.removeCallbacks(holdRunnable)
                        if (isHolding) {
                            isHolding = false
                            stopAudioCaptureAndProcess()
                        } else {
                            if (event.action == MotionEvent.ACTION_UP) toggleDictation()
                        }
                    }
                }
                true
            }
        }
        bottomRow.addView(flowBtn)
        
        mainContainer.addView(bottomRow)

        return mainContainer
    }

    private fun createToolbarButton(textStr: String, bgColor: String, textColor: String, onClick: () -> Unit): Button {
        val density = resources.displayMetrics.density
        return Button(this).apply {
            text = textStr
            setTextColor(Color.parseColor(textColor))
            isAllCaps = false
            textSize = 12f
            
            val drawable = GradientDrawable().apply {
                setColor(Color.parseColor(bgColor))
                cornerRadius = 16f * density
            }
            background = drawable
            
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, (35 * density).toInt()).apply {
                setMargins((2 * density).toInt(), 0, (2 * density).toInt(), 0)
            }
            setPadding((10 * density).toInt(), 0, (10 * density).toInt(), 0)
            
            setOnTouchListener { v, event ->
                if (event.action == MotionEvent.ACTION_DOWN) v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                false
            }
            setOnClickListener { onClick() }
        }
    }

    private fun createKeyButton(textStr: String, isSpecial: Boolean, weight: Float = 1f, longPressAction: (() -> Unit)? = null, onClick: () -> Unit): Button {
        val density = resources.displayMetrics.density
        return Button(this).apply {
            text = textStr
            setTextColor(Color.WHITE)
            isAllCaps = false
            textSize = 20f
            
            val defaultColor = if (isSpecial) "#1A1A1A" else "#222222"
            val pressedColor = "#444444"
            
            background = GradientDrawable().apply {
                setColor(Color.parseColor(defaultColor))
                cornerRadius = 8f * density
            }
            
            layoutParams = LinearLayout.LayoutParams(0, (45 * density).toInt(), weight).apply {
                setMargins((1 * density).toInt(), (2 * density).toInt(), (1 * density).toInt(), (2 * density).toInt())
            }
            setPadding(0, 0, 0, 0)
            
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

    private fun updateShiftState() {
        keyButtons.forEach { btn ->
            val currentText = btn.text.toString()
            btn.text = if (isShifted) currentText.uppercase() else currentText.lowercase()
        }
    }

    private fun rewriteText() {
        coroutineScope.launch {
            val ic = currentInputConnection
            val text = ic?.getExtractedText(android.view.inputmethod.ExtractedTextRequest(), 0)?.text?.toString()
            if (text.isNullOrBlank()) return@launch
            
            dictationButton.text = "✨..."
            val prompt = "Rewrite and professionalize this text. Output only the final text, no quotes or intro: $text"
            val newText = formatWithGemini(prompt, "gemini-3.5-flash")
            
            withContext(Dispatchers.Main) {
                ic.deleteSurroundingText(10000, 10000)
                ic.commitText(newText, 1)
                updateUI()
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

    private fun toggleDictation() {
        isRecording = !isRecording
        updateUI()
        if (isRecording) startAudioCapture() else stopAudioCaptureAndProcess()
    }

    private fun updateUI() {
        if (isRecording) {
            dictationButton.text = "🔴 Rec"
            dictationButton.setTextColor(Color.RED)
        } else {
            dictationButton.text = "🎤 Flow"
            dictationButton.setTextColor(Color.WHITE)
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
        
        dictationButton.text = "⏳ Proc"
        dictationButton.setTextColor(Color.parseColor("#4A90E2"))

        val pcmData = audioBuffer.toByteArray()
        if (pcmData.isEmpty()) { updateUI(); return }
        val wavData = createWavData(pcmData, sampleRate, 1)

        coroutineScope.launch {
            try {
                val transcript = transcribeWithGroq(wavData)
                if (transcript.isNullOrBlank()) { withContext(Dispatchers.Main) { updateUI() }; return@launch }

                val chatterRegex = "(?i)chatter[\\\\s,]+(.*)".toRegex()
                val match = chatterRegex.find(transcript)
                val prompt = if (match != null) {
                    "The user issued an interactive prompt command: '${match.groupValues[1].trim()}'. Generate a helpful and direct response to insert."
                } else {
                    "Format this dictation cleanly: $transcript"
                }

                val formattedText = formatWithGemini(prompt, "gemini-3.5-flash")
                withContext(Dispatchers.Main) {
                    currentInputConnection?.commitText(formattedText, 1)
                    updateUI()
                }
            } catch (e: Exception) {
                Log.e("FlowDictation", "Error processing audio", e)
                withContext(Dispatchers.Main) {
                    dictationButton.text = "❌ Err"
                    dictationButton.setTextColor(Color.RED)
                    Handler(Looper.getMainLooper()).postDelayed({ updateUI() }, 2000)
                }
            }
        }
    }

    private fun createWavData(pcmData: ByteArray, sampleRate: Int, channels: Int): ByteArray {
        val totalDataLen = pcmData.size + 36
        val byteRate = sampleRate * channels * 2
        val header = ByteBuffer.allocate(44).apply {
            order(ByteOrder.LITTLE_ENDIAN)
            put("RIFF".toByteArray())
            putInt(totalDataLen)
            put("WAVE".toByteArray())
            put("fmt ".toByteArray())
            putInt(16)
            putShort(1)
            putShort(channels.toShort())
            putInt(sampleRate)
            putInt(byteRate)
            putShort((channels * 2).toShort())
            putShort(16)
            put("data".toByteArray())
            putInt(pcmData.size)
        }.array()
        return header + pcmData
    }

    private suspend fun transcribeWithGroq(audioData: ByteArray): String? = withContext(Dispatchers.IO) {
        val client = OkHttpClient()
        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", "audio.wav", audioData.toRequestBody("audio/wav".toMediaType()))
            .addFormDataPart("model", "whisper-large-v3")
            .addFormDataPart("response_format", "json")
            .build()
        val request = Request.Builder()
            .url("https://api.groq.com/openai/v1/audio/transcriptions")
            .addHeader("Authorization", "Bearer $groqApiKey")
            .post(requestBody)
            .build()
        val response = client.newCall(request).execute()
        val bodyStr = response.body?.string()
        if (response.isSuccessful && bodyStr != null) {
            return@withContext JSONObject(bodyStr).optString("text")
        }
        return@withContext null
    }

    private suspend fun formatWithGemini(prompt: String, model: String): String = withContext(Dispatchers.IO) {
        val generativeModel = GenerativeModel(
            modelName = model,
            apiKey = geminiApiKey,
            systemInstruction = content {
                text("You are a highly capable AI text formatter for a dictation app. Your job is to take raw, messy transcribed audio and convert it into clean, grammatically correct prose. Remove all filler words (ums, ahs, stutters, repeated words). Add appropriate punctuation and capitalization. If the user explicitly says 'comma', 'period', 'exclamation point', 'question mark', 'new paragraph', or 'open quote'/'close quote', insert the correct punctuation mark or formatting instead of the word.\\n\\nSelf-Correction Rules:\\nIf the user says \\"scratch that\\", \\"no wait\\", \\"actually\\", or audibly corrects themselves mid-sentence (e.g., \\"Schedule a meeting for 6 PM. Scratch that, make it 7 PM\\"), you MUST intelligently apply the correction, remove the mistaken phrase, and output ONLY the final intended meaning. Do not include the correction keywords in the final output.\\n\\nCRITICAL INSTRUCTION: YOU MUST ONLY OUTPUT THE FINAL FORMATTED TEXT. NEVER output the original raw text. NEVER include prefaces or explanations. JUST the polished text.")
            }
        )
        return@withContext generativeModel.generateContent(prompt).text?.trim() ?: ""
    }
}
""")

with open(r"C:\Users\z_tes\.gemini\antigravity\scratch\flow-dictation\android-client\app\src\main\java\com\example\flowdictation\FlowDictationIME.kt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("V3 Kotlin file generated successfully!")
