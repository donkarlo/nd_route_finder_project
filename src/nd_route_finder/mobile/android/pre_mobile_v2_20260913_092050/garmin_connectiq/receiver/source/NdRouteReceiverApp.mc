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
    var _pendingName = null;
    var _openAttempts = 0;

    function initialize() {
        AppBase.initialize();
        _openTimer = new Timer.Timer();
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

    function onPhoneMessage(message) {
        try {
            if (message == null || message.data == null) {
                gReceiverStatus = "Empty phone message";
                WatchUi.requestUpdate();
                return;
            }
            var data = message.data;
            if (data["type"] != "point") {
                gReceiverStatus = "Unsupported message";
                WatchUi.requestUpdate();
                return;
            }

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

            // Avoid selecting an older app-owned waypoint with the same name.
            var oldItems = PersistedContent.getAppWaypoints();
            var oldItem = oldItems.next();
            while (oldItem != null) {
                if (oldItem.getName() == pointName) {
                    oldItem.remove();
                }
                oldItem = oldItems.next();
            }

            PersistedContent.saveWaypoint(location, { :name => pointName });
            _pendingName = pointName;
            _openAttempts = 0;
            gReceiverStatus = "Saving waypoint…";
            WatchUi.requestUpdate();

            // Persistence may not be visible in the iterator in the same instant.
            // Poll briefly, then hand the persisted waypoint to Garmin's native UI.
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
            var items = PersistedContent.getAppWaypoints();
            var item = items.next();
            while (item != null) {
                if (_pendingName != null && item.getName() == _pendingName) {
                    _openTimer.stop();
                    gReceiverStatus = "Opening Garmin navigation…";
                    WatchUi.requestUpdate();
                    System.exitTo(item.toIntent());
                    return;
                }
                item = items.next();
            }

            if (_openAttempts >= 12) {
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
