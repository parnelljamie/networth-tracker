package com.passbook.app

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import kotlin.concurrent.thread

/**
 * docs/07-mobile.md "Android shell": starts the Python backend (app/mobile.py) on a local port in
 * this process and shows its web UI full screen. Everything else is the same code as the PC.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private val main = Handler(Looper.getMainLooper())

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        webView = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            webViewClient = LocalOnlyClient()
            addJavascriptInterface(Bridge(), "PassbookAndroid")
        }
        val root = FrameLayout(this).apply { addView(webView) }
        setContentView(root)

        // Android 15 draws apps edge to edge: keep the page clear of the status and navigation
        // bars, and of the keyboard.
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        showMessage("Opening Waymark…", "")
        thread(name = "passbook-start") { startServer() }
    }

    private fun startServer() {
        try {
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(applicationContext))
            }
            val resources = unpackResources()
            val data = File(filesDir, "data").apply { mkdirs() }
            // Returns the same port if the server is already running in this process.
            val port = Python.getInstance()
                .getModule("app.mobile")
                .callAttr("start", data.absolutePath, resources.absolutePath)
                .toInt()
            main.post { webView.loadUrl("http://127.0.0.1:$port/") }
        } catch (e: Throwable) {
            Log.e(TAG, "Waymark failed to start", e)
            main.post { showMessage("Waymark couldn't start", e.toString()) }
        }
    }

    /** Copies assets/resources to private storage, once per installed version. */
    private fun unpackResources(): File {
        val target = File(filesDir, "resources")
        val stamp = packageManager.getPackageInfo(packageName, 0).lastUpdateTime.toString()
        val marker = File(target, ".installed")
        if (marker.exists() && marker.readText() == stamp) return target
        target.deleteRecursively()
        copyAsset("resources", target)
        marker.writeText(stamp)
        return target
    }

    private fun copyAsset(path: String, dest: File) {
        val children = assets.list(path).orEmpty()
        if (children.isEmpty()) {
            dest.parentFile?.mkdirs()
            assets.open(path).use { input -> dest.outputStream().use { input.copyTo(it) } }
            return
        }
        dest.mkdirs()
        for (child in children) copyAsset("$path/$child", File(dest, child))
    }

    private fun showMessage(title: String, detail: String) {
        val html = """
            <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
              body { font-family: sans-serif; display: flex; flex-direction: column; align-items: center;
                     justify-content: center; height: 100vh; margin: 0; padding: 0 24px; text-align: center;
                     color: #1a1e28; background: #f5f2ea; }
              @media (prefers-color-scheme: dark) { body { color: #ede7da; background: #15130f; } }
              p { color: #6a665c; font-size: 13px; word-break: break-word; }
            </style></head>
            <body><h3>${escape(title)}</h3><p>${escape(detail)}</p></body></html>
        """.trimIndent()
        webView.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)
    }

    private fun escape(s: String) = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    /** Only the app's own server loads inside the app; any other link opens in the browser. */
    private inner class LocalOnlyClient : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            if (request.url.host == "127.0.0.1") return false
            startActivity(Intent(Intent.ACTION_VIEW, request.url))
            return true
        }
    }

    /** `window.PassbookAndroid` in the page (frontend/src/lib/android.ts). */
    private inner class Bridge {
        @JavascriptInterface
        fun scanQrCode() {
            main.post {
                val options = GmsBarcodeScannerOptions.Builder()
                    .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                    .build()
                GmsBarcodeScanning.getClient(this@MainActivity, options).startScan()
                    .addOnSuccessListener { deliverScan(it.rawValue) }
                    .addOnCanceledListener { deliverScan(null) }
                    .addOnFailureListener { e ->
                        Log.w(TAG, "QR scan failed", e)
                        deliverScan(null)
                    }
            }
        }

        /**
         * Settings -> Updates: downloads the release APK and hands it to Android's installer, which
         * asks the user to confirm. Progress goes back through `window.onPassbookUpdateStatus`.
         */
        @JavascriptInterface
        fun installUpdate(url: String, sha256: String?) {
            val uri = Uri.parse(url)
            if (uri.scheme != "https" || uri.host != "github.com") {
                deliverUpdateStatus(JSONObject().put("state", "error").put("error", "Not a GitHub download link"))
                return
            }
            if (!packageManager.canRequestPackageInstalls()) {
                // A one-time switch: "Allow from this source" for Waymark.
                deliverUpdateStatus(JSONObject().put("state", "permission"))
                main.post {
                    startActivity(
                        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName"))
                    )
                }
                return
            }
            thread(name = "passbook-update") { downloadAndInstall(url, sha256) }
        }
    }

    private fun downloadAndInstall(url: String, sha256: String?) {
        try {
            val folder = File(cacheDir, "updates").apply { deleteRecursively(); mkdirs() }
            val apk = File(folder, "update.apk")
            val digest = MessageDigest.getInstance("SHA-256")
            val connection = URL(url).openConnection() as HttpURLConnection
            connection.connectTimeout = 20_000
            connection.readTimeout = 60_000
            connection.instanceFollowRedirects = true
            connection.inputStream.use { input ->
                apk.outputStream().use { output ->
                    val total = connection.contentLengthLong
                    val buffer = ByteArray(1 shl 16)
                    var done = 0L
                    var lastReport = 0L
                    while (true) {
                        val n = input.read(buffer)
                        if (n < 0) break
                        output.write(buffer, 0, n)
                        digest.update(buffer, 0, n)
                        done += n
                        if (done - lastReport > 512 * 1024) {
                            lastReport = done
                            deliverUpdateStatus(
                                JSONObject().put("state", "downloading").put("downloaded", done).put("total", total)
                            )
                        }
                    }
                }
            }
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            if (!sha256.isNullOrEmpty() && !actual.equals(sha256, ignoreCase = true)) {
                apk.delete()
                throw IllegalStateException("The download didn't match GitHub's checksum, so it wasn't installed.")
            }
            val content = FileProvider.getUriForFile(this, "$packageName.updates", apk)
            val intent = Intent(Intent.ACTION_VIEW)
                .setDataAndType(content, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            deliverUpdateStatus(JSONObject().put("state", "installing"))
            main.post { startActivity(intent) }
        } catch (e: Exception) {
            Log.w(TAG, "Update failed", e)
            deliverUpdateStatus(JSONObject().put("state", "error").put("error", e.message ?: e.toString()))
        }
    }

    private fun deliverUpdateStatus(status: JSONObject) {
        main.post {
            webView.evaluateJavascript("window.onPassbookUpdateStatus && window.onPassbookUpdateStatus($status)", null)
        }
    }

    private fun deliverScan(text: String?) {
        val arg = if (text == null) "null" else JSONObject.quote(text)
        webView.evaluateJavascript("window.onPassbookQrScanned && window.onPassbookQrScanned($arg)", null)
    }

    private companion object {
        const val TAG = "Passbook"
    }
}
