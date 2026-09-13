package com.ndroutefinder.mobile;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.net.ssl.HttpsURLConnection;

public final class RouteEngine {
    public interface ResultCallback {
        void onSuccess(GpxCodec.Track track, boolean constraintFallback, String note);
        void onFailure(String message);
    }

    public interface SearchCallback {
        void onSuccess(JSONArray results);
        void onFailure(String message);
    }

    private static final String USER_AGENT = "nd_route_finder_mobile/1.0 (personal route planner)";
    private static final String BROUTER_URL = "https://brouter.de/brouter";
    private static final String NOMINATIM_URL = "https://nominatim.openstreetmap.org/search";
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    public void shutdown() {
        executor.shutdownNow();
    }

    public void searchPlaces(String query, SearchCallback callback) {
        executor.execute(() -> {
            try {
                String clean = query == null ? "" : query.trim();
                if (clean.length() < 2) throw new IllegalArgumentException("Type at least two characters.");
                String url = NOMINATIM_URL + "?format=jsonv2&limit=6&addressdetails=0&q="
                        + URLEncoder.encode(clean, "UTF-8");
                String body = httpGet(url, "application/json");
                JSONArray raw = new JSONArray(body);
                JSONArray out = new JSONArray();
                for (int i = 0; i < raw.length(); i++) {
                    JSONObject item = raw.optJSONObject(i);
                    if (item == null) continue;
                    JSONObject compact = new JSONObject();
                    compact.put("lat", Double.parseDouble(item.getString("lat")));
                    compact.put("lon", Double.parseDouble(item.getString("lon")));
                    compact.put("label", item.optString("display_name", "Result"));
                    out.put(compact);
                }
                callback.onSuccess(out);
            } catch (Exception e) {
                callback.onFailure(readable(e));
            }
        });
    }

    public void generate(String requestJson, ResultCallback callback) {
        executor.execute(() -> {
            try {
                Request request = Request.fromJson(new JSONObject(requestJson));
                List<List<GpxCodec.Point>> candidates = buildCandidateCoordinates(request);
                if (candidates.isEmpty()) throw new IllegalStateException("No route candidates could be created.");

                List<ScoredTrack> scored = new ArrayList<>();
                Exception lastError = null;
                int index = 0;
                for (List<GpxCodec.Point> candidate : candidates) {
                    try {
                        String trackName = "ND_" + request.activity + "_" + (++index);
                        String gpx = requestBrouter(candidate, profileFor(request.activity), trackName);
                        GpxCodec.Track track = GpxCodec.parse(gpx, trackName);
                        scored.add(score(track, request));
                    } catch (Exception e) {
                        lastError = e;
                    }
                }

                if (scored.isEmpty()) {
                    throw new IllegalStateException(
                            lastError == null ? "BRouter returned no usable route." : readable(lastError)
                    );
                }

                Collections.sort(scored, Comparator.comparingDouble(item -> item.score));
                ScoredTrack best = scored.get(0);
                boolean fallback = !best.withinSlope;
                String note;
                if (fallback) {
                    String slopeText = best.track.maxGradePercent == null
                            ? "unknown slope"
                            : String.format(Locale.US, "max slope %.1f%%", best.track.maxGradePercent);
                    note = String.format(Locale.US,
                            "Closest route used: %.2f km, %s. No candidate met the requested slope limit.",
                            best.track.distanceM / 1000.0, slopeText);
                } else {
                    note = String.format(Locale.US,
                            "Generated route: %.2f km%s.",
                            best.track.distanceM / 1000.0,
                            best.track.maxGradePercent == null
                                    ? ""
                                    : String.format(Locale.US, ", max slope %.1f%%", best.track.maxGradePercent));
                }
                callback.onSuccess(best.track, fallback, note);
            } catch (Exception e) {
                callback.onFailure(readable(e));
            }
        });
    }

    private static final class Request {
        final double startLat;
        final double startLon;
        final String activity;
        final double targetDistanceKm;
        final double maxGradePercent;
        final List<GpxCodec.Point> waypoints;

        Request(double startLat, double startLon, String activity,
                double targetDistanceKm, double maxGradePercent, List<GpxCodec.Point> waypoints) {
            this.startLat = startLat;
            this.startLon = startLon;
            this.activity = activity;
            this.targetDistanceKm = targetDistanceKm;
            this.maxGradePercent = maxGradePercent;
            this.waypoints = waypoints;
        }

        static Request fromJson(JSONObject json) throws Exception {
            double lat = json.getDouble("startLat");
            double lon = json.getDouble("startLon");
            if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
                throw new IllegalArgumentException("Start coordinates are outside valid latitude/longitude ranges.");
            }
            String activity = json.optString("activity", "cycling").toLowerCase(Locale.ROOT);
            double distanceKm = json.optDouble("distanceKm", 20.0);
            if (distanceKm < 1.0 || distanceKm > 150.0) {
                throw new IllegalArgumentException("Target distance must be between 1 and 150 km.");
            }
            double maxGrade = json.optDouble("maxGrade", 12.0);
            if (maxGrade < 1.0 || maxGrade > 60.0) {
                throw new IllegalArgumentException("Maximum slope must be between 1 and 60 percent.");
            }
            List<GpxCodec.Point> waypoints = new ArrayList<>();
            JSONArray arr = json.optJSONArray("waypoints");
            if (arr != null) {
                for (int i = 0; i < arr.length(); i++) {
                    JSONObject item = arr.optJSONObject(i);
                    if (item == null) continue;
                    double wLat = item.getDouble("lat");
                    double wLon = item.getDouble("lon");
                    if (wLat < -90 || wLat > 90 || wLon < -180 || wLon > 180) continue;
                    waypoints.add(new GpxCodec.Point(wLat, wLon, null));
                }
            }
            return new Request(lat, lon, activity, distanceKm, maxGrade, waypoints);
        }
    }

    private static final class ScoredTrack {
        final GpxCodec.Track track;
        final double score;
        final boolean withinSlope;

        ScoredTrack(GpxCodec.Track track, double score, boolean withinSlope) {
            this.track = track;
            this.score = score;
            this.withinSlope = withinSlope;
        }
    }

    private ScoredTrack score(GpxCodec.Track track, Request request) {
        double targetM = request.targetDistanceKm * 1000.0;
        double lengthError = Math.abs(track.distanceM - targetM) / Math.max(1.0, targetM);
        boolean slopeKnown = track.maxGradePercent != null;
        boolean withinSlope = !slopeKnown || track.maxGradePercent <= request.maxGradePercent;
        double slopePenalty = 0.0;
        if (slopeKnown && track.maxGradePercent > request.maxGradePercent) {
            slopePenalty = 2.0 + (track.maxGradePercent - request.maxGradePercent) / Math.max(1.0, request.maxGradePercent);
        }
        return new ScoredTrack(track, lengthError + slopePenalty, withinSlope);
    }

    private List<List<GpxCodec.Point>> buildCandidateCoordinates(Request request) {
        GpxCodec.Point start = new GpxCodec.Point(request.startLat, request.startLon, null);
        List<List<GpxCodec.Point>> out = new ArrayList<>();
        if (request.waypoints.isEmpty()) {
            double targetM = request.targetDistanceKm * 1000.0;
            // A three-corner loop with this radius typically lands near the requested distance
            // after the road/trail network adds realistic detours.
            double baseRadius = Math.max(250.0, targetM / 5.2);
            double[] factors = {0.72, 0.88, 1.02, 1.18, 1.34};
            double[] rotations = {15.0, 73.0, 137.0, 211.0, 287.0};
            for (int i = 0; i < factors.length; i++) {
                double radius = baseRadius * factors[i];
                double rotation = rotations[i];
                List<GpxCodec.Point> points = new ArrayList<>();
                points.add(start);
                points.add(destination(start, radius, rotation));
                points.add(destination(start, radius, rotation + 120.0));
                points.add(destination(start, radius, rotation + 240.0));
                points.add(start);
                out.add(points);
            }
        } else {
            List<GpxCodec.Point> base = new ArrayList<>();
            base.add(start);
            base.addAll(request.waypoints);
            base.add(start);
            out.add(base);

            double directEstimate = polylineDistance(base);
            double targetM = request.targetDistanceKm * 1000.0;
            if (directEstimate < targetM * 0.93) {
                GpxCodec.Point center = centroid(base);
                double missing = Math.max(500.0, targetM - directEstimate);
                double detourRadius = Math.min(Math.max(500.0, missing / 2.7), targetM * 0.28);
                double[] angles = {35.0, 105.0, 185.0, 265.0, 325.0};
                for (int i = 0; i < angles.length; i++) {
                    GpxCodec.Point detour = destination(center, detourRadius, angles[i]);
                    List<GpxCodec.Point> candidate = new ArrayList<>();
                    candidate.add(start);
                    int slot = i % (request.waypoints.size() + 1);
                    for (int w = 0; w < request.waypoints.size(); w++) {
                        if (w == slot) candidate.add(detour);
                        candidate.add(request.waypoints.get(w));
                    }
                    if (slot == request.waypoints.size()) candidate.add(detour);
                    candidate.add(start);
                    out.add(candidate);
                }
            }
        }
        return out;
    }

    private static double polylineDistance(List<GpxCodec.Point> points) {
        double sum = 0.0;
        for (int i = 1; i < points.size(); i++) sum += GpxCodec.distance(points.get(i - 1), points.get(i));
        return sum;
    }

    private static GpxCodec.Point centroid(List<GpxCodec.Point> points) {
        double lat = 0.0, lon = 0.0;
        for (GpxCodec.Point p : points) { lat += p.latitude; lon += p.longitude; }
        return new GpxCodec.Point(lat / points.size(), lon / points.size(), null);
    }

    private static GpxCodec.Point destination(GpxCodec.Point origin, double distanceM, double bearingDeg) {
        double radius = 6_371_008.8;
        double angular = distanceM / radius;
        double bearing = Math.toRadians(bearingDeg);
        double lat1 = Math.toRadians(origin.latitude);
        double lon1 = Math.toRadians(origin.longitude);
        double lat2 = Math.asin(Math.sin(lat1) * Math.cos(angular)
                + Math.cos(lat1) * Math.sin(angular) * Math.cos(bearing));
        double lon2 = lon1 + Math.atan2(
                Math.sin(bearing) * Math.sin(angular) * Math.cos(lat1),
                Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2)
        );
        return new GpxCodec.Point(Math.toDegrees(lat2), normalizeLongitude(Math.toDegrees(lon2)), null);
    }

    private static double normalizeLongitude(double lon) {
        double value = lon;
        while (value > 180.0) value -= 360.0;
        while (value < -180.0) value += 360.0;
        return value;
    }

    private String requestBrouter(List<GpxCodec.Point> points, String profile, String trackName) throws Exception {
        StringBuilder lonLats = new StringBuilder();
        for (int i = 0; i < points.size(); i++) {
            if (i > 0) lonLats.append('|');
            GpxCodec.Point p = points.get(i);
            lonLats.append(String.format(Locale.US, "%.7f,%.7f", p.longitude, p.latitude));
        }
        String url = BROUTER_URL
                + "?lonlats=" + URLEncoder.encode(lonLats.toString(), "UTF-8")
                + "&profile=" + URLEncoder.encode(profile, "UTF-8")
                + "&alternativeidx=0&format=gpx&trackname="
                + URLEncoder.encode(trackName, "UTF-8");
        return httpGet(url, "application/gpx+xml,application/xml,text/xml,*/*");
    }

    private static String profileFor(String activity) {
        switch (activity) {
            case "hiking":
            case "walking":
                // Hiking profile deliberately permits paths that cycling profiles reject.
                return "hiking-mountain";
            case "cycling":
            default:
                return "trekking";
        }
    }

    private static String httpGet(String urlText, String accept) throws Exception {
        URL url = new URL(urlText);
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(20_000);
        connection.setReadTimeout(45_000);
        connection.setRequestProperty("User-Agent", USER_AGENT);
        connection.setRequestProperty("Accept", accept);
        connection.setInstanceFollowRedirects(true);
        int code = connection.getResponseCode();
        InputStream stream = code >= 200 && code < 300 ? connection.getInputStream() : connection.getErrorStream();
        if (stream == null) throw new IllegalStateException("HTTP " + code);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int count;
        while ((count = stream.read(buffer)) >= 0) out.write(buffer, 0, count);
        stream.close();
        connection.disconnect();
        String body = new String(out.toByteArray(), StandardCharsets.UTF_8);
        if (code < 200 || code >= 300) {
            String compact = body.replaceAll("\\s+", " ").trim();
            if (compact.length() > 220) compact = compact.substring(0, 220) + "…";
            throw new IllegalStateException("Routing server HTTP " + code + (compact.isEmpty() ? "" : ": " + compact));
        }
        return body;
    }

    private static String readable(Throwable error) {
        String message = error.getMessage();
        if (message == null || message.trim().isEmpty()) message = error.getClass().getSimpleName();
        return message;
    }
}
