package com.ndroutefinder.mobile;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;

import com.garmin.android.connectiq.ConnectIQ;
import com.garmin.android.connectiq.IQApp;
import com.garmin.android.connectiq.IQDevice;
import com.garmin.android.connectiq.exception.InvalidStateException;
import com.garmin.android.connectiq.exception.ServiceUnavailableException;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class GarminBridge {
    // Must match garmin_connectiq/*/manifest.xml.
    public static final String RECEIVER_APP_ID = "5e82dd20fec746dd923adccbed6070e0";
    public static final String DATAFIELD_APP_ID = "dec5fcce14a648369fe555933c4ab9b6";

    public interface Listener {
        void onStatus(String text);
    }

    private final Context context;
    private final Listener listener;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService sdkExecutor = Executors.newSingleThreadExecutor();
    private ConnectIQ connectIQ;
    private boolean sdkReady;

    public GarminBridge(Context context, Listener listener) {
        this.context = context.getApplicationContext();
        this.listener = listener;
    }

    public void initialize() {
        try {
            connectIQ = ConnectIQ.getInstance(context, ConnectIQ.IQConnectType.WIRELESS);
            connectIQ.initialize(context, true, new ConnectIQ.ConnectIQListener() {
                @Override
                public void onSdkReady() {
                    sdkReady = true;
                    sdkExecutor.execute(GarminBridge.this::reportConnectedDevice);
                }

                @Override
                public void onInitializeError(ConnectIQ.IQSdkErrorStatus errStatus) {
                    sdkReady = false;
                    emit("Garmin: Connect IQ SDK init failed: " + errStatus);
                }

                @Override
                public void onSdkShutDown() {
                    sdkReady = false;
                    emit("Garmin: SDK stopped.");
                }
            });
        } catch (RuntimeException e) {
            sdkReady = false;
            emit("Garmin: Garmin Connect is required for phone↔watch communication.");
        }
    }

    public void refresh() {
        if (!sdkReady) {
            emit("Garmin: SDK is not ready. Make sure Garmin Connect is installed and the watch is paired.");
            return;
        }
        sdkExecutor.execute(this::reportConnectedDevice);
    }

    public void sendPointToCurrentActivity(double lat, double lon, String name) {
        sendPoint(DATAFIELD_APP_ID, lat, lon, name, false);
    }

    public void sendPointAndOpenNativeNavigation(double lat, double lon, String name) {
        sendPoint(RECEIVER_APP_ID, lat, lon, name, true);
    }

    private void sendPoint(String appId, double lat, double lon, String name, boolean openAfterSend) {
        if (!sdkReady || connectIQ == null) {
            emit("Garmin: SDK is not ready yet.");
            return;
        }
        sdkExecutor.execute(() -> {
            IQDevice device = chooseConnectedDevice();
            if (device == null) {
                emit("Garmin: no connected watch found in Garmin Connect.");
                return;
            }

            Map<String, Object> payload = new HashMap<>();
            payload.put("type", "point");
            payload.put("lat", lat);
            payload.put("lon", lon);
            payload.put("name", (name == null || name.trim().isEmpty()) ? "ND point" : name.trim());
            payload.put("source", "nd_route_finder_mobile");

            IQApp app = new IQApp(appId);
            try {
                connectIQ.sendMessage(device, app, payload, (iqDevice, iqApp, status) ->
                        emit("Garmin: point message status: " + status + " — " + friendlyName(iqDevice))
                );
                if (openAfterSend) {
                    // Phone messages are queued by Connect IQ. Give Garmin Connect a short moment
                    // before prompting the user to open the receiver watch app.
                    mainHandler.postDelayed(() -> sdkExecutor.execute(() -> openReceiver(device)), 650L);
                } else {
                    emit("Garmin: point sent to 'ND Route Target'. Keep that data field added to the active activity.");
                }
            } catch (InvalidStateException | ServiceUnavailableException e) {
                emit("Garmin: could not send point: " + message(e));
            } catch (RuntimeException e) {
                emit("Garmin: point send failed: " + message(e));
            }
        });
    }

    private void openReceiver(IQDevice device) {
        if (!sdkReady || connectIQ == null) return;
        IQApp app = new IQApp(RECEIVER_APP_ID);
        try {
            connectIQ.openApplication(device, app, (iqDevice, iqApp, status) -> {
                emit("Garmin: watch launch status: " + status
                        + ". Accept the prompt on the watch; Garmin will then offer native navigation/activity choices.");
            });
        } catch (InvalidStateException | ServiceUnavailableException e) {
            emit("Garmin: could not open receiver app: " + message(e));
        } catch (RuntimeException e) {
            emit("Garmin: could not open receiver app: " + message(e));
        }
    }

    private void reportConnectedDevice() {
        IQDevice device = chooseConnectedDevice();
        if (device == null) {
            emit("Garmin: SDK ready, but no connected watch is currently available.");
        } else {
            emit("Garmin connected: " + friendlyName(device));
        }
    }

    private IQDevice chooseConnectedDevice() {
        if (!sdkReady || connectIQ == null) return null;
        try {
            List<IQDevice> connected = connectIQ.getConnectedDevices();
            if (connected != null && !connected.isEmpty()) return connected.get(0);
        } catch (InvalidStateException | ServiceUnavailableException ignored) {
        }

        try {
            List<IQDevice> known = connectIQ.getKnownDevices();
            if (known != null) {
                for (IQDevice device : known) {
                    try {
                        if (connectIQ.getDeviceStatus(device) == IQDevice.IQDeviceStatus.CONNECTED) {
                            return device;
                        }
                    } catch (Exception ignored) {
                    }
                }
            }
        } catch (InvalidStateException | ServiceUnavailableException ignored) {
        }
        return null;
    }

    private static String friendlyName(IQDevice device) {
        if (device == null) return "Garmin device";
        String name = device.getFriendlyName();
        return name == null || name.trim().isEmpty() ? "Garmin device" : name;
    }

    private void emit(String text) {
        mainHandler.post(() -> listener.onStatus(text));
    }

    public void shutdown() {
        if (connectIQ != null) {
            try {
                connectIQ.unregisterAllForEvents();
            } catch (Exception ignored) {
            }
            try {
                connectIQ.shutdown(context);
            } catch (Exception ignored) {
            }
        }
        sdkReady = false;
        sdkExecutor.shutdownNow();
    }

    private static String message(Throwable e) {
        String msg = e.getMessage();
        return msg == null || msg.trim().isEmpty() ? e.getClass().getSimpleName() : msg;
    }
}
