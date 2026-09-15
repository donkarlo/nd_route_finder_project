#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
GPX_CODEC="$ROOT/app/src/main/java/com/ndroutefinder/mobile/GpxCodec.java"

python3 - "$GPX_CODEC" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

old = '''        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(false);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        Document doc = factory.newDocumentBuilder().parse(
                new ByteArrayInputStream(gpx.getBytes(StandardCharsets.UTF_8))
        );
'''

new = '''        String upperGpx = gpx.toUpperCase(Locale.ROOT);
        if (upperGpx.contains("<!DOCTYPE") || upperGpx.contains("<!ENTITY")) {
            throw new IllegalArgumentException("GPX files containing DOCTYPE or ENTITY declarations are not supported.");
        }

        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(false);
        setXmlFeatureIfSupported(factory, "http://apache.org/xml/features/disallow-doctype-decl", true);
        setXmlFeatureIfSupported(factory, "http://xml.org/sax/features/external-general-entities", false);
        setXmlFeatureIfSupported(factory, "http://xml.org/sax/features/external-parameter-entities", false);
        setXmlFeatureIfSupported(factory, "http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
        factory.setExpandEntityReferences(false);

        Document doc = factory.newDocumentBuilder().parse(
                new ByteArrayInputStream(gpx.getBytes(StandardCharsets.UTF_8))
        );
'''

helper = '''    private static void setXmlFeatureIfSupported(DocumentBuilderFactory factory, String feature, boolean value) {
        try {
            factory.setFeature(feature, value);
        } catch (Exception ignored) {
            // Android XML implementations do not all support the same feature set.
            // The explicit DOCTYPE/ENTITY rejection above keeps local GPX loading safe.
        }
    }

'''

if old in text:
    backup = path.with_name(path.name + ".pre_android_xml_feature_fix_20260915.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")

    text = text.replace(old, new, 1)
    marker = "    private static List<Point> readPoints(Document doc, String tag) {"
    if helper not in text:
        if marker not in text:
            raise SystemExit("Could not find helper insertion point in GpxCodec.java")
        text = text.replace(marker, helper + marker, 1)

    path.write_text(text, encoding="utf-8")
    print("Fixed Android GPX parser: unsupported XML parser features are now optional.")
    print(f"Backup: {backup}")
elif "setXmlFeatureIfSupported(factory" in text:
    print("Android GPX parser fix is already present.")
else:
    raise SystemExit("GpxCodec.java did not match the expected source; no change was made.")
PY

exec "$ROOT/build_and_install.sh"
