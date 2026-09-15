package com.ndroutefinder.mobile;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import javax.xml.parsers.DocumentBuilderFactory;

public final class GpxCodec {
    private static final double EARTH_RADIUS_M = 6_371_008.8;

    public static final class Point {
        public final double latitude;
        public final double longitude;
        public final Double elevation;

        public Point(double latitude, double longitude, Double elevation) {
            this.latitude = latitude;
            this.longitude = longitude;
            this.elevation = elevation;
        }
    }

    public static final class Track {
        public final List<Point> points;
        public final double distanceM;
        public final Double maxGradePercent;
        public final String gpx;
        public final String name;

        public Track(List<Point> points, String gpx, String name) {
            this.points = points;
            this.gpx = gpx;
            this.name = name == null || name.trim().isEmpty() ? "ND route" : name.trim();
            this.distanceM = calculateDistance(points);
            this.maxGradePercent = calculateSmoothedMaxGrade(points);
        }

        public JSONObject toJson(boolean includePoints) throws JSONException {
            JSONObject out = new JSONObject();
            out.put("name", name);
            out.put("distanceKm", distanceM / 1000.0);
            if (maxGradePercent == null) {
                out.put("maxGrade", JSONObject.NULL);
            } else {
                out.put("maxGrade", maxGradePercent);
            }
            if (includePoints) {
                JSONArray arr = new JSONArray();
                int step = Math.max(1, points.size() / 3500);
                for (int i = 0; i < points.size(); i += step) {
                    Point p = points.get(i);
                    JSONArray pair = new JSONArray();
                    pair.put(p.latitude);
                    pair.put(p.longitude);
                    if (p.elevation != null) pair.put(p.elevation);
                    arr.put(pair);
                }
                if (!points.isEmpty() && (points.size() - 1) % step != 0) {
                    Point p = points.get(points.size() - 1);
                    JSONArray pair = new JSONArray();
                    pair.put(p.latitude);
                    pair.put(p.longitude);
                    if (p.elevation != null) pair.put(p.elevation);
                    arr.put(pair);
                }
                out.put("points", arr);
            }
            return out;
        }
    }

    private GpxCodec() {}

    public static Track parse(String gpx, String fallbackName) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(false);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        Document doc = factory.newDocumentBuilder().parse(
                new ByteArrayInputStream(gpx.getBytes(StandardCharsets.UTF_8))
        );

        String name = firstText(doc, "name");
        if (name == null || name.trim().isEmpty()) name = fallbackName;

        List<Point> points = readPoints(doc, "trkpt");
        if (points.size() < 2) points = readPoints(doc, "rtept");
        if (points.size() < 2) points = readPoints(doc, "wpt");
        if (points.size() < 2) {
            throw new IllegalArgumentException("GPX does not contain a route with at least two points.");
        }
        return new Track(points, gpx, name);
    }

    private static List<Point> readPoints(Document doc, String tag) {
        NodeList nodes = doc.getElementsByTagName(tag);
        List<Point> points = new ArrayList<>(nodes.getLength());
        for (int i = 0; i < nodes.getLength(); i++) {
            Node node = nodes.item(i);
            if (!(node instanceof Element)) continue;
            Element element = (Element) node;
            try {
                double lat = Double.parseDouble(element.getAttribute("lat"));
                double lon = Double.parseDouble(element.getAttribute("lon"));
                Double ele = null;
                NodeList elevations = element.getElementsByTagName("ele");
                if (elevations.getLength() > 0) {
                    String text = elevations.item(0).getTextContent();
                    if (text != null && !text.trim().isEmpty()) {
                        ele = Double.parseDouble(text.trim());
                    }
                }
                points.add(new Point(lat, lon, ele));
            } catch (RuntimeException ignored) {
            }
        }
        return points;
    }

    private static String firstText(Document doc, String tag) {
        NodeList list = doc.getElementsByTagName(tag);
        if (list.getLength() == 0) return null;
        String text = list.item(0).getTextContent();
        return text == null ? null : text.trim();
    }

    public static String buildWaypoint(String name, double lat, double lon) {
        String safeName = escapeXml(name == null || name.trim().isEmpty() ? "ND point" : name.trim());
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                + "<gpx version=\"1.1\" creator=\"ND Route Finder\" xmlns=\"http://www.topografix.com/GPX/1/1\">\n"
                + String.format(Locale.US,
                "  <wpt lat=\"%.8f\" lon=\"%.8f\"><name>%s</name><sym>Flag</sym><type>Waypoint</type></wpt>\n",
                lat, lon, safeName)
                + "</gpx>\n";
    }

    public static String buildTrack(String name, List<Point> points) {
        String safeName = escapeXml(name == null ? "ND route" : name);
        StringBuilder out = new StringBuilder(512 + points.size() * 64);
        out.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
                .append("<gpx version=\"1.1\" creator=\"ND Route Finder\" xmlns=\"http://www.topografix.com/GPX/1/1\">\n")
                .append("  <trk><name>").append(safeName).append("</name><trkseg>\n");
        for (Point p : points) {
            out.append(String.format(Locale.US, "    <trkpt lat=\"%.8f\" lon=\"%.8f\">", p.latitude, p.longitude));
            if (p.elevation != null) {
                out.append(String.format(Locale.US, "<ele>%.2f</ele>", p.elevation));
            }
            out.append("</trkpt>\n");
        }
        out.append("  </trkseg></trk>\n</gpx>\n");
        return out.toString();
    }

    private static String escapeXml(String value) {
        return value.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&apos;");
    }

    public static double calculateDistance(List<Point> points) {
        double total = 0.0;
        for (int i = 1; i < points.size(); i++) {
            total += distance(points.get(i - 1), points.get(i));
        }
        return total;
    }

    public static Double calculateSmoothedMaxGrade(List<Point> points) {
        if (points.size() < 2) return null;
        for (Point p : points) {
            if (p.elevation == null) return null;
        }

        double[] cumulative = new double[points.size()];
        for (int i = 1; i < points.size(); i++) {
            cumulative[i] = cumulative[i - 1] + distance(points.get(i - 1), points.get(i));
        }
        if (cumulative[cumulative.length - 1] < 30.0) return null;

        double maxAbs = 0.0;
        int left = 0;
        for (int right = 1; right < points.size(); right++) {
            while (left + 1 < right && cumulative[right] - cumulative[left + 1] >= 100.0) {
                left++;
            }
            double horizontal = cumulative[right] - cumulative[left];
            if (horizontal < 45.0) continue;
            double rise = points.get(right).elevation - points.get(left).elevation;
            double grade = Math.abs(100.0 * rise / horizontal);
            if (Double.isFinite(grade)) maxAbs = Math.max(maxAbs, grade);
        }
        return maxAbs;
    }

    public static double distance(Point first, Point second) {
        double lat1 = Math.toRadians(first.latitude);
        double lat2 = Math.toRadians(second.latitude);
        double dLat = lat2 - lat1;
        double dLon = Math.toRadians(second.longitude - first.longitude);
        double a = Math.sin(dLat / 2.0) * Math.sin(dLat / 2.0)
                + Math.cos(lat1) * Math.cos(lat2)
                * Math.sin(dLon / 2.0) * Math.sin(dLon / 2.0);
        return 2.0 * EARTH_RADIUS_M * Math.asin(Math.min(1.0, Math.sqrt(a)));
    }
}
