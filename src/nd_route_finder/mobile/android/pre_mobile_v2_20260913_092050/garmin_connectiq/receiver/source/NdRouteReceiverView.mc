import Toybox.Graphics;
import Toybox.WatchUi;

class NdRouteReceiverView extends WatchUi.View {
    function onUpdate(dc) {
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_BLACK);
        dc.clear();
        var cx = dc.getWidth() / 2;
        var cy = dc.getHeight() / 2;
        dc.drawText(cx, cy - 28, Graphics.FONT_SMALL, "ND Route Receiver", Graphics.TEXT_JUSTIFY_CENTER);
        dc.drawText(cx, cy + 6, Graphics.FONT_XTINY, gReceiverStatus, Graphics.TEXT_JUSTIFY_CENTER);
    }
}
