import Toybox.Activity;
import Toybox.Communications;
import Toybox.Position;
import Toybox.WatchUi;

class NdRouteTargetField extends WatchUi.SimpleDataField {
    var _label = "ND target ready";
    var _pendingLocation = null;
    var _pendingName = null;
    var _remainingRouteAttempts = 0;

    function initialize() {
        SimpleDataField.initialize();
        label = "ND Route";
        Communications.registerForPhoneAppMessages(method(:onPhoneMessage));
    }

    function compute(info as Activity.Info) {
        // compute() is called by Garmin once per second for an active data field.
        // If routeTo() was called before the newly-selected activity was ready,
        // keep retrying here instead of requiring a second tap on the phone.
        if (_pendingLocation != null && _remainingRouteAttempts > 0) {
            _attemptRoute();
        }

        return _label;
    }

    function onPhoneMessage(message as Communications.PhoneAppMessage) as Void {
        try {
            if (message == null || message.data == null) {
                _clearPendingRoute();
                _label = "No target";
                WatchUi.requestUpdate();
                return;
            }

            var data = message.data;
            _pendingLocation = new Position.Location({
                :latitude => data["lat"],
                :longitude => data["lon"],
                :format => :degrees
            });

            var pointName = data["name"];
            _pendingName = pointName == null ? "Navigating" : pointName;

            // One immediate attempt plus subsequent once-per-second retries
            // from compute(), for ten attempts total.
            _remainingRouteAttempts = 10;
            _label = "Waiting for activity";
            _attemptRoute();
            WatchUi.requestUpdate();
        } catch (error) {
            _clearPendingRoute();
            _label = "Target error";
            WatchUi.requestUpdate();
        }
    }

    function _attemptRoute() as Void {
        if (_pendingLocation == null || _remainingRouteAttempts <= 0) {
            return;
        }

        try {
            var ok = routeTo(_pendingLocation, null);
            if (ok) {
                _label = _pendingName == null ? "Navigating" : _pendingName;
                _clearPendingRoute();
                return;
            }

            _remainingRouteAttempts -= 1;
            if (_remainingRouteAttempts <= 0) {
                _label = "Route rejected";
                _clearPendingRoute();
            } else {
                _label = "Waiting for activity";
            }
        } catch (error) {
            _remainingRouteAttempts -= 1;
            if (_remainingRouteAttempts <= 0) {
                _label = "Target error";
                _clearPendingRoute();
            } else {
                _label = "Waiting for activity";
            }
        }
    }

    function _clearPendingRoute() as Void {
        _pendingLocation = null;
        _pendingName = null;
        _remainingRouteAttempts = 0;
    }
}
