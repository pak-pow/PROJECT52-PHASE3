/**
 * Device Frame Simulator Controller
 * Enables switching between iPhone 15, Pixel 8, iPad, and Full Responsive viewports.
 */

"use strict";

export const DeviceFrame = {
    init() {
        const selector = document.getElementById("device-selector");
        const frameContainer = document.getElementById("device-frame-container");
        if (!selector || !frameContainer) return;

        const savedDevice = localStorage.getItem("pulse_device_view") || "responsive";
        selector.value = savedDevice;
        this.applyDevice(savedDevice);

        selector.addEventListener("change", (e) => {
            const device = e.target.value;
            this.applyDevice(device);
            localStorage.setItem("pulse_device_view", device);
        });
    },

    applyDevice(device) {
        const frameContainer = document.getElementById("device-frame-container");
        if (!frameContainer) return;

        // Reset classes
        frameContainer.classList.remove(
            "frame-iphone15",
            "frame-pixel8",
            "frame-ipad",
            "frame-responsive"
        );

        switch (device) {
            case "iphone15":
                frameContainer.classList.add("frame-iphone15");
                break;
            case "pixel8":
                frameContainer.classList.add("frame-pixel8");
                break;
            case "ipad":
                frameContainer.classList.add("frame-ipad");
                break;
            default:
                frameContainer.classList.add("frame-responsive");
                break;
        }
    },
};
