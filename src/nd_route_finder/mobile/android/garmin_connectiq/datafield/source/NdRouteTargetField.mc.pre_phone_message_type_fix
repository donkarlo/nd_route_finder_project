import Toybox.Activity;
import Toybox.Communications;
import Toybox.Position;
import Toybox.WatchUi;

class NdRouteTargetField extends WatchUi.SimpleDataField {
    var _label = "ND target ready";

    function initialize() {
        SimpleDataField.initialize();
        label = "ND Route";
        Communications.registerForPhoneAppMessages(method(:onPhoneMessage));
    }

    function compute(info as Activity.Info) {
        return _label;
    }

    function onPhoneMessage(message) {
        try {
            if (message == null || message.data == null) {
                _label = "No target";
                WatchUi.requestUpdate();
                return;
            }
            var data = message.data;
            if (data["type"] != "point") {
                _label = "Bad target";
                WatchUi.requestUpdate();
                return;
            }

            var location = new Position.Location({
                :latitude => data["lat"],
                :longitude => data["lon"],
                :format => :degrees
            });
            var ok = routeTo(location, null);
            if (ok) {
                var pointName = data["name"];
                _label = pointName == null ? "Navigating" : pointName;
            } else {
                _label = "Route rejected";
            }
            WatchUi.requestUpdate();
        } catch (error) {
            _label = "Target error";
            WatchUi.requestUpdate();
        }
    }
}
