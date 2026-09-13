import Toybox.Application;
import Toybox.Communications;
import Toybox.Position;
import Toybox.PersistedContent;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;

var gReceiverStatus = "Waiting for phone…";

class NdRouteReceiverApp extends Application.AppBase {
    var _openTimer = null;
    var _openAttempts = 0;
    var _knownWaypointIds = null;

    function initialize() {
        AppBase.initialize();
        _openTimer = new Timer.Timer();
        _knownWaypointIds = {};
    }

    function onStart(state) {
        gReceiverStatus = "Waiting for route target…";
        Communications.registerForPhoneAppMessages(method(:onPhoneMessage));
    }

    function onStop(state) {
        if (_openTimer != null) {
            _openTimer.stop();
        }
    }

    function getInitialView() {
        return [ new NdRouteReceiverView() ];
    }

    function onPhoneMessage(message as Communications.PhoneAppMessage) as Void {
        try {
            if (message == null || message.data == null) {
                gReceiverStatus = "Empty phone message";
                WatchUi.requestUpdate();
                return;
            }

            var data = message.data;
            var latitude = data["lat"];
            var longitude = data["lon"];
            var pointName = data["name"];
            if (pointName == null) {
                pointName = "ND point";
            }

            var location = new Position.Location({
                :latitude => latitude,
                :longitude => longitude,
                :format => :degrees
            });

            // Snapshot every waypoint ID that exists before saving the new
            // target. The Fenix 8 does not reliably refresh getAppWaypoints()
            // immediately after saveWaypoint(), so detect the new waypoint
            // from the global collection instead.
            _knownWaypointIds = {};
            var beforeItems = PersistedContent.getWaypoints();
            var beforeItem = beforeItems.next();
            while (beforeItem != null) {
                _knownWaypointIds[beforeItem.getId()] = true;
                beforeItem = beforeItems.next();
            }

            PersistedContent.saveWaypoint(location, { :name => pointName });

            _openAttempts = 0;
            gReceiverStatus = "Opening activity chooser…";
            WatchUi.requestUpdate();

            // Poll the global waypoint list for up to ~20 seconds. The first
            // ID that was not present before saveWaypoint() is the new target.
            _openTimer.stop();
            _openTimer.start(method(:tryOpenWaypoint), 250, true);
        } catch (error) {
            gReceiverStatus = "Target error";
            System.println(error);
            WatchUi.requestUpdate();
        }
    }

    function tryOpenWaypoint() {
        try {
            _openAttempts += 1;

            var items = PersistedContent.getWaypoints();
            var item = items.next();

            while (item != null) {
                if (!_knownWaypointIds.hasKey(item.getId())) {
                    _openTimer.stop();
                    gReceiverStatus = "Choose activity…";
                    WatchUi.requestUpdate();
                    System.exitTo(item.toIntent());
                    return;
                }

                item = items.next();
            }

            if (_openAttempts >= 80) {
                _openTimer.stop();
                gReceiverStatus = "Waypoint saved; open Locations";
                WatchUi.requestUpdate();
            }
        } catch (error) {
            _openTimer.stop();
            gReceiverStatus = "Open navigation error";
            System.println(error);
            WatchUi.requestUpdate();
        }
    }
}
