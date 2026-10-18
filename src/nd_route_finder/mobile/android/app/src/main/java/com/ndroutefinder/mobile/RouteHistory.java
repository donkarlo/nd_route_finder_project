package com.ndroutefinder.mobile;

import android.content.Context;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** Historical GPX reference positions, snapshotted from Dropbox on Ubuntu. */
final class RouteHistory {
    private static final double GRID_M = 40.0;
    private static final double NEAR_M = 42.0;
    private static final double LAT_M = 111195.0;
    private static final double LON_M = LAT_M * Math.cos(Math.toRadians(47.1));
    private final Map<Long, List<double[]>> cells = new HashMap<>();
    private int routeCount = 0;
    private int pointCount = 0;

    RouteHistory(Context context) {
        // Android packaging transparently expands .gz assets and strips their
        // .gz suffix. The APK therefore contains history_gpx_points.csv.
        try (InputStream asset = context.getAssets().open("history_gpx_points.csv");
             BufferedReader reader = new BufferedReader(new InputStreamReader(asset, StandardCharsets.US_ASCII))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.startsWith("#routes=")) {
                    routeCount = Integer.parseInt(line.substring(8));
                    continue;
                }
                String[] values = line.split(",", 2);
                if (values.length != 2) continue;
                double lat = Double.parseDouble(values[0]);
                double lon = Double.parseDouble(values[1]);
                double x = lon * LON_M, y = lat * LAT_M;
                int cx = (int) Math.floor(x / GRID_M);
                int cy = (int) Math.floor(y / GRID_M);
                cells.computeIfAbsent(cellKey(cx, cy), ignored -> new ArrayList<>())
                        .add(new double[]{x, y});
                pointCount++;
            }
            android.util.Log.i("NDRouteFinder", "Loaded GPX history: " + routeCount
                    + " tracks, " + pointCount + " sampled points");
        } catch (Exception error) {
            // An unavailable/corrupt snapshot cannot block ordinary routing.
            android.util.Log.w("NDRouteFinder", "Offline GPX snapshot unavailable", error);
            cells.clear();
            routeCount = 0;
            pointCount = 0;
        }
    }

    int routeCount() { return routeCount; }

    double overlapRatio(List<GpxCodec.Point> points) {
        if (pointCount == 0 || points == null || points.size() < 2) return 0.0;
        double nextM = 0.0;
        int near = 0, total = 0;
        GpxCodec.Point previous = null;
        double distance = 0.0;
        for (GpxCodec.Point point : points) {
            if (previous != null) distance += GpxCodec.distance(previous, point);
            previous = point;
            if (distance < nextM) continue;
            nextM = distance + 36.0;
            total++;
            if (containsNearby(point)) near++;
        }
        return near / (double) Math.max(1, total);
    }

    private boolean containsNearby(GpxCodec.Point point) {
        double x = point.longitude * LON_M, y = point.latitude * LAT_M;
        int gx = (int) Math.floor(x / GRID_M), gy = (int) Math.floor(y / GRID_M);
        double threshold2 = NEAR_M * NEAR_M;
        for (int dx = -2; dx <= 2; dx++) {
            for (int dy = -2; dy <= 2; dy++) {
                List<double[]> candidates = cells.get(cellKey(gx + dx, gy + dy));
                if (candidates == null) continue;
                for (double[] candidate : candidates) {
                    double a = x - candidate[0], b = y - candidate[1];
                    if (a*a + b*b <= threshold2) return true;
                }
            }
        }
        return false;
    }

    private static long cellKey(int x, int y) {
        return (((long) x) << 32) | (y & 0xFFFFFFFFL);
    }
}
