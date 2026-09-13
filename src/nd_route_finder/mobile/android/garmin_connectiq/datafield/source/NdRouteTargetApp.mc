import Toybox.Application;

class NdRouteTargetApp extends Application.AppBase {
    function initialize() {
        AppBase.initialize();
    }

    function getInitialView() {
        return [ new NdRouteTargetField() ];
    }
}
