package com.ndroutefinder.mobile;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public final class MainActivity extends Activity {
    private static final int REQUEST_OPEN_GPX = 4102;
    private static final String GARMIN_CONNECT_PACKAGE = "com.garmin.android.apps.connectmobile";

    private WebView webView;
    private RouteEngine routeEngine;
    private GarminBridge garminBridge;
    private GpxCodec.Track currentTrack;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        routeEngine = new RouteEngine();
        garminBridge = new GarminBridge(this, this::onGarminStatus);

        webView = new WebView(this);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setLoadsImagesAutomatically(true);
        settings.setUserAgentString(settings.getUserAgentString() + " nd_route_finder_mobile/1.0");
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setBuiltInZoomControls(false);
        // The UI is an app asset while Leaflet tiles/scripts are HTTPS resources.
        settings.setAllowUniversalAccessFromFileURLs(true);

        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient());
        webView.addJavascriptInterface(new NativeBridge(), "Android");
        setContentView(webView);
        webView.loadUrl("file:///android_asset/route_finder.html");

        garminBridge.initialize();
    }

    private final class NativeBridge {
        @JavascriptInterface
        public void searchPlaces(String query) {
            routeEngine.searchPlaces(query, new RouteEngine.SearchCallback() {
                @Override
                public void onSuccess(JSONArray results) {
                    callJs("window.ndSearchResults(" + results.toString() + ");");
                }

                @Override
                public void onFailure(String message) {
                    callJs("window.ndSearchFailed(" + JSONObject.quote(message) + ");");
                }
            });
        }

        @JavascriptInterface
        public void generateRoute(String requestJson) {
            callJs("window.ndSetBusy(true, 'Calculating route…');");
            routeEngine.generate(requestJson, new RouteEngine.ResultCallback() {
                @Override
                public void onSuccess(GpxCodec.Track track, boolean constraintFallback, String note) {
                    currentTrack = track;
                    try {
                        JSONObject payload = track.toJson(true);
                        payload.put("fallback", constraintFallback);
                        payload.put("note", note);
                        cacheCurrentRoute(track);
                        callJs("window.ndRouteReady(" + payload.toString() + ");");
                    } catch (Exception e) {
                        callJs("window.ndRouteFailed(" + JSONObject.quote(message(e)) + ");");
                    }
                }

                @Override
                public void onFailure(String message) {
                    callJs("window.ndRouteFailed(" + JSONObject.quote(message) + ");");
                }
            });
        }

        @JavascriptInterface
        public void pickGpx() {
            runOnUiThread(() -> {
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{
                        "application/gpx+xml", "application/xml", "text/xml", "application/octet-stream"
                });
                startActivityForResult(intent, REQUEST_OPEN_GPX);
            });
        }

        @JavascriptInterface
        public void refreshGarmin() {
            garminBridge.refresh();
        }

        @JavascriptInterface
        public void sendPointToCurrentActivity(double lat, double lon, String name) {
            garminBridge.sendPointToCurrentActivity(lat, lon, name);
        }

        @JavascriptInterface
        public void openPointOnGarmin(double lat, double lon, String name) {
            garminBridge.sendPointAndOpenNativeNavigation(lat, lon, name);
        }

        @JavascriptInterface
        public void sendRouteToGarminConnect() {
            runOnUiThread(MainActivity.this::sendCurrentRouteToGarminConnect);
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_OPEN_GPX || resultCode != RESULT_OK || data == null || data.getData() == null) {
            return;
        }
        Uri uri = data.getData();
        try {
            String gpx = readText(uri, 30 * 1024 * 1024);
            GpxCodec.Track track = GpxCodec.parse(gpx, "Loaded GPX");
            currentTrack = track;
            cacheCurrentRoute(track);
            JSONObject payload = track.toJson(true);
            payload.put("fallback", false);
            payload.put("note", String.format(Locale.US, "Loaded GPX: %.2f km", track.distanceM / 1000.0));
            callJs("window.ndLoadedGpx(" + payload.toString() + ");");
        } catch (Exception e) {
            callJs("window.ndRouteFailed(" + JSONObject.quote("Could not load GPX: " + message(e)) + ");");
        }
    }

    private String readText(Uri uri, int maxBytes) throws Exception {
        InputStream input = getContentResolver().openInputStream(uri);
        if (input == null) throw new IllegalStateException("Could not open selected file.");
        try (InputStream in = input; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int total = 0;
            int count;
            while ((count = in.read(buffer)) >= 0) {
                total += count;
                if (total > maxBytes) throw new IllegalArgumentException("GPX file is too large.");
                out.write(buffer, 0, count);
            }
            return new String(out.toByteArray(), StandardCharsets.UTF_8);
        }
    }

    private File cacheCurrentRoute(GpxCodec.Track track) throws Exception {
        File dir = new File(getCacheDir(), "garmin_share");
        if (!dir.exists() && !dir.mkdirs()) throw new IllegalStateException("Could not create route cache.");
        File file = new File(dir, "nd_route_current.gpx");
        try (FileOutputStream output = new FileOutputStream(file, false)) {
            output.write(track.gpx.getBytes(StandardCharsets.UTF_8));
        }
        return file;
    }

    private void sendCurrentRouteToGarminConnect() {
        if (currentTrack == null) {
            toast("Generate or load a GPX route first.");
            onGarminStatus("Garmin: no route is loaded.");
            return;
        }
        try {
            File file = cacheCurrentRoute(currentTrack);
            Uri uri = new Uri.Builder()
                    .scheme("content")
                    .authority(GpxProvider.AUTHORITY)
                    .appendPath(file.getName())
                    .build();

            if (tryGarminConnectView(uri)) return;
            if (tryGarminConnectShare(uri)) return;

            Intent chooser = Intent.createChooser(createViewIntent(uri), "Import GPX with");
            startActivity(chooser);
            onGarminStatus("Garmin Connect was not opened directly. Choose Garmin Connect, then save the course and Send to Device.");
        } catch (Exception e) {
            toast("Could not share GPX: " + message(e));
            onGarminStatus("Garmin route share failed: " + message(e));
        }
    }

    private boolean tryGarminConnectView(Uri uri) {
        String[] mimeTypes = new String[]{
                "application/gpx+xml",
                "application/octet-stream",
                "application/xml",
                "text/xml"
        };
        for (String mimeType : mimeTypes) {
            Intent intent = createViewIntent(uri, mimeType);
            intent.setPackage(GARMIN_CONNECT_PACKAGE);
            try {
                startActivity(intent);
                onGarminStatus("GPX opened in Garmin Connect. Import/save it as a course, then Send to Device.");
                return true;
            } catch (ActivityNotFoundException ignored) {
            }
        }
        return false;
    }

    private boolean tryGarminConnectShare(Uri uri) {
        String[] mimeTypes = new String[]{
                "application/gpx+xml",
                "application/octet-stream"
        };
        for (String mimeType : mimeTypes) {
            Intent intent = new Intent(Intent.ACTION_SEND);
            intent.setType(mimeType);
            intent.putExtra(Intent.EXTRA_STREAM, uri);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            intent.setClipData(ClipData.newUri(getContentResolver(), "GPX", uri));
            intent.setPackage(GARMIN_CONNECT_PACKAGE);
            try {
                startActivity(intent);
                onGarminStatus("GPX shared to Garmin Connect. Import/save it as a course, then Send to Device.");
                return true;
            } catch (ActivityNotFoundException ignored) {
            }
        }
        return false;
    }

    private Intent createViewIntent(Uri uri) {
        return createViewIntent(uri, "application/gpx+xml");
    }

    private Intent createViewIntent(Uri uri, String mimeType) {
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, mimeType);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        intent.setClipData(ClipData.newUri(getContentResolver(), "GPX", uri));
        return intent;
    }

    private void onGarminStatus(String text) {
        callJs("window.ndGarminStatus(" + JSONObject.quote(text) + ");");
    }

    private void callJs(String script) {
        runOnUiThread(() -> {
            if (webView != null) webView.evaluateJavascript(script, null);
        });
    }

    private void toast(String text) {
        runOnUiThread(() -> Toast.makeText(this, text, Toast.LENGTH_LONG).show());
    }

    private static String message(Throwable e) {
        String text = e.getMessage();
        return text == null || text.trim().isEmpty() ? e.getClass().getSimpleName() : text;
    }

    @Override
    protected void onDestroy() {
        if (garminBridge != null) garminBridge.shutdown();
        if (routeEngine != null) routeEngine.shutdown();
        if (webView != null) {
            webView.removeJavascriptInterface("Android");
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
