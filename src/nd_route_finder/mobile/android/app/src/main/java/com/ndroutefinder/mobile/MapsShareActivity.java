package com.ndroutefinder.mobile;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.widget.TextView;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Android share target for Google Maps locations.
 *
 * Flow:
 * Google Maps -> Share -> ND Route Finder -> resolve coordinates -> Garmin.
 * If an activity containing the ND Route Target data field is currently active,
 * its telemetry response is used as the signal to route inside that activity.
 * Otherwise the receiver app is opened so Garmin can offer its native activity
 * selection/navigation flow.
 */
public final class MapsShareActivity extends Activity {
    private static final long ACTIVE_ACTIVITY_DETECTION_MS = 2800L;
    private static final int MAX_REDIRECTS = 7;
    private static final int MAX_HTML_CHARS = 160_000;

    private static final Pattern URL_PATTERN = Pattern.compile("https?://\\S+");
    private static final Pattern AT_COORDS = Pattern.compile(
            "@(-?\\d{1,2}(?:\\.\\d+)?),(-?\\d{1,3}(?:\\.\\d+)?)");
    private static final Pattern DATA_COORDS = Pattern.compile(
            "!3d(-?\\d{1,2}(?:\\.\\d+)?)!4d(-?\\d{1,3}(?:\\.\\d+)?)");
    private static final Pattern GEO_COORDS = Pattern.compile(
            "geo:(-?\\d{1,2}(?:\\.\\d+)?),(-?\\d{1,3}(?:\\.\\d+)?)",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern DECIMAL_PAIR = Pattern.compile(
            "(?<![0-9.])(-?\\d{1,2}\\.\\d{4,})\\s*[,; ]\\s*(-?\\d{1,3}\\.\\d{4,})(?![0-9.])");

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService resolverExecutor = Executors.newSingleThreadExecutor();

    private TextView statusView;
    private GarminBridge garminBridge;
    private Target pendingTarget;
    private boolean detectionStarted;
    private boolean dispatched;
    private Runnable fallbackRunnable;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        showStatus("Reading Google Maps destination…");

        String sharedText = extractSharedText(getIntent());
        if (sharedText == null || sharedText.trim().isEmpty()) {
            fail("No Google Maps location was shared.");
            return;
        }

        garminBridge = new GarminBridge(this, new GarminBridge.Listener() {
            @Override
            public void onStatus(String text) {
                showStatus(text);
                if (text != null && text.startsWith("Garmin connected:")) {
                    beginActiveActivityDetection();
                }
            }

            @Override
            public void onLocation(double lat, double lon, double headingDeg,
                                   double accuracyM, double speedMps, long timestampMs) {
                // A location reply proves the ND Route Target data field is alive
                // inside an active Garmin activity.
                if (!dispatched && detectionStarted && pendingTarget != null) {
                    dispatchToActiveActivity();
                }
            }
        });

        resolveTargetAsync(sharedText);
        garminBridge.initialize();
    }

    private void resolveTargetAsync(String sharedText) {
        Target direct = parseTarget(sharedText, titleFromSharedText(sharedText));
        if (direct != null) {
            pendingTarget = direct;
            showStatus(String.format(Locale.US,
                    "Destination %.6f, %.6f found. Connecting to Garmin…",
                    direct.lat, direct.lon));
            return;
        }

        String sharedUrl = firstUrl(sharedText);
        if (sharedUrl == null) {
            fail("The shared Google Maps text did not contain usable coordinates or a link.");
            return;
        }

        showStatus("Resolving Google Maps link…");
        resolverExecutor.execute(() -> {
            try {
                String resolved = resolveGoogleMapsUrl(sharedUrl);
                Target target = parseTarget(resolved, titleFromSharedText(sharedText));
                if (target == null) {
                    handler.post(() -> fail("Google Maps link resolved, but no coordinates were found."));
                    return;
                }
                handler.post(() -> {
                    pendingTarget = target;
                    showStatus(String.format(Locale.US,
                            "Destination %.6f, %.6f found. Connecting to Garmin…",
                            target.lat, target.lon));
                    beginActiveActivityDetection();
                });
            } catch (Exception e) {
                handler.post(() -> fail("Could not resolve Google Maps link: " + message(e)));
            }
        });
    }

    private void beginActiveActivityDetection() {
        if (dispatched || detectionStarted || pendingTarget == null || garminBridge == null) return;
        detectionStarted = true;
        showStatus("Checking for an active Garmin activity…");

        garminBridge.setTelemetryEnabled(true);
        fallbackRunnable = () -> {
            if (!dispatched) dispatchToNativeGarminNavigation();
        };
        handler.postDelayed(fallbackRunnable, ACTIVE_ACTIVITY_DETECTION_MS);
    }

    private void dispatchToActiveActivity() {
        if (dispatched || pendingTarget == null || garminBridge == null) return;
        dispatched = true;
        cancelFallback();
        garminBridge.setTelemetryEnabled(false);
        showStatus("Active Garmin activity detected. Sending destination to its native navigation…");
        garminBridge.sendPointToCurrentActivity(pendingTarget.lat, pendingTarget.lon, pendingTarget.name);
        handler.postDelayed(this::finish, 3200L);
    }

    private void dispatchToNativeGarminNavigation() {
        if (dispatched || pendingTarget == null || garminBridge == null) return;
        dispatched = true;
        cancelFallback();
        garminBridge.setTelemetryEnabled(false);
        showStatus("No active ND Route Target detected. Opening Garmin native navigation/activity selection…");
        garminBridge.sendPointAndOpenNativeNavigation(pendingTarget.lat, pendingTarget.lon, pendingTarget.name);
        // GarminBridge opens the receiver after a short delay. Keep this Activity
        // alive long enough for that Connect IQ handoff to finish.
        handler.postDelayed(this::finish, 5000L);
    }

    private void cancelFallback() {
        if (fallbackRunnable != null) {
            handler.removeCallbacks(fallbackRunnable);
            fallbackRunnable = null;
        }
    }

    private static String extractSharedText(Intent intent) {
        if (intent == null) return null;
        if (Intent.ACTION_SEND.equals(intent.getAction())) {
            CharSequence text = intent.getCharSequenceExtra(Intent.EXTRA_TEXT);
            if (text != null) return text.toString();
        }
        Uri data = intent.getData();
        return data == null ? null : data.toString();
    }

    private static String titleFromSharedText(String text) {
        if (text == null) return "Google Maps destination";
        String[] lines = text.trim().split("\\r?\\n");
        for (String line : lines) {
            String clean = line.trim();
            if (!clean.isEmpty() && !clean.startsWith("http://") && !clean.startsWith("https://")) {
                return clean.length() > 80 ? clean.substring(0, 80) : clean;
            }
        }
        return "Google Maps destination";
    }

    private static String firstUrl(String text) {
        if (text == null) return null;
        Matcher matcher = URL_PATTERN.matcher(text);
        if (!matcher.find()) return null;
        String url = matcher.group();
        while (url.endsWith(".") || url.endsWith(",") || url.endsWith(")") || url.endsWith("]")) {
            url = url.substring(0, url.length() - 1);
        }
        return url;
    }

    private static Target parseTarget(String text, String name) {
        if (text == null) return null;

        Target target = targetFromPattern(AT_COORDS, text, name);
        if (target != null) return target;
        target = targetFromPattern(DATA_COORDS, text, name);
        if (target != null) return target;
        target = targetFromPattern(GEO_COORDS, text, name);
        if (target != null) return target;

        Matcher urlMatcher = URL_PATTERN.matcher(text);
        while (urlMatcher.find()) {
            Target fromUri = targetFromUri(urlMatcher.group(), name);
            if (fromUri != null) return fromUri;
        }

        return targetFromPattern(DECIMAL_PAIR, text, name);
    }

    private static Target targetFromUri(String url, String name) {
        try {
            Uri uri = Uri.parse(url);
            String[] keys = new String[]{"query", "destination", "q", "ll", "center"};
            for (String key : keys) {
                String value = uri.getQueryParameter(key);
                if (value == null) continue;
                Target t = targetFromPattern(DECIMAL_PAIR, value, name);
                if (t != null) return t;
                t = targetFromPattern(GEO_COORDS, value, name);
                if (t != null) return t;
            }
        } catch (RuntimeException ignored) {
        }
        return null;
    }

    private static Target targetFromPattern(Pattern pattern, String text, String name) {
        Matcher matcher = pattern.matcher(text);
        while (matcher.find()) {
            try {
                double lat = Double.parseDouble(matcher.group(1));
                double lon = Double.parseDouble(matcher.group(2));
                if (validCoordinate(lat, lon)) return new Target(lat, lon, name);
            } catch (RuntimeException ignored) {
            }
        }
        return null;
    }

    private static String resolveGoogleMapsUrl(String initialUrl) throws Exception {
        String current = initialUrl;
        StringBuilder evidence = new StringBuilder(initialUrl);

        for (int i = 0; i < MAX_REDIRECTS; i++) {
            HttpURLConnection connection = (HttpURLConnection) new URL(current).openConnection();
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(7000);
            connection.setReadTimeout(7000);
            connection.setRequestProperty("User-Agent", "Mozilla/5.0 (Android) NDRouteFinder/1.0");
            connection.setRequestProperty("Accept-Language", "en-US,en;q=0.8");
            connection.setRequestMethod("GET");

            int code = connection.getResponseCode();
            String location = connection.getHeaderField("Location");
            if (code >= 300 && code < 400 && location != null && !location.trim().isEmpty()) {
                URL next = new URL(new URL(current), location);
                current = next.toString();
                evidence.append('\n').append(current);
                connection.disconnect();
                continue;
            }

            evidence.append('\n').append(connection.getURL().toString());
            InputStream stream = null;
            try {
                stream = code >= 400 ? connection.getErrorStream() : connection.getInputStream();
                if (stream != null) evidence.append('\n').append(readLimited(stream, MAX_HTML_CHARS));
            } finally {
                if (stream != null) try { stream.close(); } catch (Exception ignored) {}
                connection.disconnect();
            }
            break;
        }
        return evidence.toString();
    }

    private static String readLimited(InputStream input, int maxChars) throws Exception {
        StringBuilder out = new StringBuilder(Math.min(maxChars, 16_384));
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
            char[] buffer = new char[4096];
            int count;
            while ((count = reader.read(buffer)) >= 0 && out.length() < maxChars) {
                int allowed = Math.min(count, maxChars - out.length());
                out.append(buffer, 0, allowed);
                if (allowed < count) break;
            }
        }
        return out.toString();
    }

    private void showStatus(String text) {
        runOnUiThread(() -> {
            if (statusView == null) {
                statusView = new TextView(this);
                statusView.setTextSize(18f);
                statusView.setGravity(Gravity.CENTER);
                int padding = (int) (24 * getResources().getDisplayMetrics().density);
                statusView.setPadding(padding, padding, padding, padding);
                setContentView(statusView);
            }
            statusView.setText(text == null ? "" : text);
        });
    }

    private void fail(String text) {
        cancelFallback();
        showStatus(text + "\n\nPress Back to return to Google Maps.");
    }

    private static boolean validCoordinate(double lat, double lon) {
        return Double.isFinite(lat) && Double.isFinite(lon)
                && lat >= -90.0 && lat <= 90.0 && lon >= -180.0 && lon <= 180.0;
    }

    private static String message(Throwable error) {
        String text = error == null ? null : error.getMessage();
        return text == null || text.trim().isEmpty()
                ? (error == null ? "unknown error" : error.getClass().getSimpleName())
                : text;
    }

    @Override
    protected void onDestroy() {
        cancelFallback();
        resolverExecutor.shutdownNow();
        if (garminBridge != null) garminBridge.shutdown();
        super.onDestroy();
    }

    private static final class Target {
        final double lat;
        final double lon;
        final String name;

        Target(double lat, double lon, String name) {
            this.lat = lat;
            this.lon = lon;
            this.name = (name == null || name.trim().isEmpty()) ? "Google Maps destination" : name.trim();
        }
    }
}
