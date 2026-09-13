package com.ndroutefinder.garmin;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class MainActivity extends Activity {
    private static final int REQUEST_GPX = 1001;
    private static final String EXPLORE_PACKAGE = "com.garmin.android.apps.explore";
    private static final String GPX_MIME = "application/gpx+xml";
    private static final Pattern COORDINATE_PAIR = Pattern.compile(
            "[-+]?\\d{1,3}(?:\\.\\d+)?\\s*[,;\\s]\\s*[-+]?\\d{1,3}(?:\\.\\d+)?"
    );

    private EditText nameInput;
    private EditText latitudeInput;
    private EditText longitudeInput;
    private TextView statusView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildUi());
    }

    private View buildUi() {
        int pad = dp(18);

        ScrollView scroll = new ScrollView(this);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(pad, pad, pad, pad);
        scroll.addView(body);

        TextView title = new TextView(this);
        title.setText("ND Route Finder → Garmin");
        title.setTextSize(24);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        body.addView(title);

        TextView hint = new TextView(this);
        hint.setText(
                "Send one coordinate as a GPX waypoint, or choose an existing GPX file. " +
                "The file is opened in Garmin Explore, which can sync it to a compatible Garmin device."
        );
        hint.setTextSize(15);
        LinearLayout.LayoutParams hintLp = lp();
        hintLp.topMargin = dp(8);
        body.addView(hint, hintLp);

        nameInput = edit("Point name", InputType.TYPE_CLASS_TEXT);
        nameInput.setText("ND point");
        body.addView(nameInput, spaced());

        latitudeInput = edit("Latitude, e.g. 47.070714", decimalInputType());
        body.addView(latitudeInput, spaced());

        longitudeInput = edit("Longitude, e.g. 15.439504", decimalInputType());
        body.addView(longitudeInput, spaced());

        Button paste = button("Paste coordinates");
        paste.setOnClickListener(v -> pasteCoordinates());
        body.addView(paste, spaced());

        Button sendPoint = button("Send point to Garmin Explore");
        sendPoint.setOnClickListener(v -> sendPoint());
        body.addView(sendPoint, spaced());

        Button chooseGpx = button("Choose GPX file and send");
        chooseGpx.setOnClickListener(v -> chooseGpx());
        body.addView(chooseGpx, spaced());

        Button openExplore = button("Open Garmin Explore");
        openExplore.setOnClickListener(v -> openExplore());
        body.addView(openExplore, spaced());

        statusView = new TextView(this);
        statusView.setText("Ready.");
        statusView.setTextSize(14);
        LinearLayout.LayoutParams statusLp = spaced();
        statusLp.topMargin = dp(20);
        body.addView(statusView, statusLp);

        return scroll;
    }

    private EditText edit(String hint, int inputType) {
        EditText edit = new EditText(this);
        edit.setHint(hint);
        edit.setInputType(inputType);
        edit.setSingleLine(true);
        edit.setTextSize(17);
        return edit;
    }

    private Button button(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setTextSize(16);
        return button;
    }

    private LinearLayout.LayoutParams lp() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
    }

    private LinearLayout.LayoutParams spaced() {
        LinearLayout.LayoutParams p = lp();
        p.topMargin = dp(12);
        return p;
    }

    private int decimalInputType() {
        return InputType.TYPE_CLASS_NUMBER
                | InputType.TYPE_NUMBER_FLAG_DECIMAL
                | InputType.TYPE_NUMBER_FLAG_SIGNED;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void pasteCoordinates() {
        ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        if (clipboard == null || !clipboard.hasPrimaryClip()) {
            toast("Clipboard is empty.");
            return;
        }

        ClipData clip = clipboard.getPrimaryClip();
        if (clip == null || clip.getItemCount() == 0) {
            toast("Clipboard is empty.");
            return;
        }

        CharSequence raw = clip.getItemAt(0).coerceToText(this);
        if (raw == null) {
            toast("No text in clipboard.");
            return;
        }

        String text = raw.toString().trim();
        Matcher matcher = COORDINATE_PAIR.matcher(text);
        if (!matcher.find()) {
            toast("Could not find latitude and longitude.");
            return;
        }

        String pair = matcher.group().replace(';', ',').trim();
        String[] parts;
        if (pair.contains(",")) {
            parts = pair.split("\\s*,\\s*", 2);
        } else {
            parts = pair.split("\\s+", 2);
        }

        if (parts.length != 2) {
            toast("Could not parse coordinates.");
            return;
        }

        latitudeInput.setText(parts[0]);
        longitudeInput.setText(parts[1]);
        status("Coordinates pasted.");
    }

    private void sendPoint() {
        Double lat = parseCoordinate(latitudeInput, -90.0, 90.0, "latitude");
        if (lat == null) return;

        Double lon = parseCoordinate(longitudeInput, -180.0, 180.0, "longitude");
        if (lon == null) return;

        String name = nameInput.getText().toString().trim();
        if (name.isEmpty()) name = "ND point";

        try {
            File shareDir = new File(getCacheDir(), "garmin_share");
            if (!shareDir.exists() && !shareDir.mkdirs()) {
                throw new IllegalStateException("Could not create share directory");
            }

            String safeName = sanitizeFileName(name);
            File file = new File(shareDir, safeName + ".gpx");
            String gpx = buildWaypointGpx(name, lat, lon);

            try (FileOutputStream output = new FileOutputStream(file, false)) {
                output.write(gpx.getBytes(StandardCharsets.UTF_8));
            }

            Uri uri = new Uri.Builder()
                    .scheme("content")
                    .authority(GpxProvider.AUTHORITY)
                    .appendPath(file.getName())
                    .build();

            status(String.format(Locale.US, "Opening waypoint %.6f, %.6f in Garmin Explore…", lat, lon));
            openGpxInExplore(uri);
        } catch (Exception e) {
            status("Error: " + e.getMessage());
            toast("Could not create GPX waypoint.");
        }
    }

    private Double parseCoordinate(EditText edit, double min, double max, String label) {
        String raw = edit.getText().toString().trim().replace(',', '.');
        if (raw.isEmpty()) {
            edit.setError("Enter " + label);
            edit.requestFocus();
            return null;
        }
        try {
            double value = Double.parseDouble(raw);
            if (!Double.isFinite(value) || value < min || value > max) {
                edit.setError(label + " must be between " + min + " and " + max);
                edit.requestFocus();
                return null;
            }
            return value;
        } catch (NumberFormatException e) {
            edit.setError("Invalid " + label);
            edit.requestFocus();
            return null;
        }
    }

    private void chooseGpx() {
        Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        pick.addCategory(Intent.CATEGORY_OPENABLE);
        pick.setType("*/*");
        pick.putExtra(Intent.EXTRA_MIME_TYPES, new String[] {
                GPX_MIME,
                "application/octet-stream",
                "text/xml",
                "application/xml"
        });
        startActivityForResult(pick, REQUEST_GPX);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_GPX || resultCode != RESULT_OK || data == null) return;

        Uri uri = data.getData();
        if (uri == null) {
            toast("No file selected.");
            return;
        }

        int flags = data.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION;
        try {
            getContentResolver().takePersistableUriPermission(uri, flags);
        } catch (Exception ignored) {
        }

        status("Opening selected GPX in Garmin Explore…");
        openGpxInExplore(uri);
    }

    private void openGpxInExplore(Uri uri) {
        String[] mimeTypes = new String[] {
                GPX_MIME,
                "application/octet-stream",
                "application/xml",
                "text/xml"
        };

        for (String mimeType : mimeTypes) {
            Intent direct = createViewIntent(uri, mimeType);
            direct.setPackage(EXPLORE_PACKAGE);
            try {
                startActivity(direct);
                status("Sent to Garmin Explore. Import it there; Explore will sync it with the paired Garmin device.");
                return;
            } catch (ActivityNotFoundException ignored) {
            }
        }

        Intent send = new Intent(Intent.ACTION_SEND);
        send.setType(GPX_MIME);
        send.putExtra(Intent.EXTRA_STREAM, uri);
        send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        send.setClipData(ClipData.newUri(getContentResolver(), "GPX", uri));
        send.setPackage(EXPLORE_PACKAGE);
        try {
            startActivity(send);
            status("Shared GPX to Garmin Explore. Complete the import there.");
            return;
        } catch (ActivityNotFoundException ignored) {
        }

        try {
            Intent chooser = Intent.createChooser(createViewIntent(uri, GPX_MIME), "Open GPX with");
            startActivity(chooser);
            status("Garmin Explore was not opened directly. Choose Garmin Explore from the Android app list.");
        } catch (ActivityNotFoundException e) {
            status("No application can open this GPX file.");
            toast("Install Garmin Explore.");
            openExploreStorePage();
        }
    }

    private Intent createViewIntent(Uri uri, String mimeType) {
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, mimeType);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        intent.setClipData(ClipData.newUri(getContentResolver(), "GPX", uri));
        return intent;
    }

    private void openExplore() {
        Intent launch = getPackageManager().getLaunchIntentForPackage(EXPLORE_PACKAGE);
        if (launch != null) {
            startActivity(launch);
        } else {
            openExploreStorePage();
        }
    }

    private void openExploreStorePage() {
        Uri market = Uri.parse("market://details?id=" + EXPLORE_PACKAGE);
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, market));
        } catch (ActivityNotFoundException e) {
            startActivity(new Intent(
                    Intent.ACTION_VIEW,
                    Uri.parse("https://play.google.com/store/apps/details?id=" + EXPLORE_PACKAGE)
            ));
        }
    }

    private String buildWaypointGpx(String name, double lat, double lon) {
        String escaped = escapeXml(name);
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                + "<gpx version=\"1.1\" creator=\"ND Route Finder Garmin Sender\" "
                + "xmlns=\"http://www.topografix.com/GPX/1/1\" "
                + "xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" "
                + "xsi:schemaLocation=\"http://www.topografix.com/GPX/1/1 "
                + "http://www.topografix.com/GPX/1/1/gpx.xsd\">\n"
                + "  <metadata><name>" + escaped + "</name></metadata>\n"
                + String.format(Locale.US,
                    "  <wpt lat=\"%.8f\" lon=\"%.8f\"><name>%s</name><sym>Flag</sym><type>Waypoint</type></wpt>\n",
                    lat, lon, escaped)
                + "</gpx>\n";
    }

    private String escapeXml(String value) {
        return value
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&apos;");
    }

    private String sanitizeFileName(String value) {
        String s = value.trim().replaceAll("[^A-Za-z0-9._-]+", "_");
        s = s.replaceAll("_+", "_");
        if (s.isEmpty()) s = "nd_point";
        if (s.length() > 60) s = s.substring(0, 60);
        return s;
    }

    private void status(String text) {
        statusView.setText(text);
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_LONG).show();
    }
}
