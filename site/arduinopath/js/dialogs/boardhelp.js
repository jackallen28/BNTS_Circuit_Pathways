// "Can't see your board?": help when the browser's box doesn't list the
// student's board, and the USB way (usbserial.js) for computers without the
// board's driver.
//
// A website can't install a driver. Most computers already have one (or get
// one from Windows Update), and the USB way needs none, so this box walks the
// student through the likely fixes for their kind of computer.

import { messageBox } from "../widgets/window.js";
import { requestUsbPort, usbSupported } from "../realboard.js";

/** "windows", "mac", "chromeos", "android", "linux" or "" (unknown). */
export function platformOf(nav = globalThis.navigator) {
  const p = `${nav?.userAgentData?.platform || ""} ${nav?.platform || ""} ${nav?.userAgent || ""}`;
  if (/android/i.test(p)) return "android";
  if (/cros|chrome os/i.test(p)) return "chromeos";
  if (/win/i.test(p)) return "windows";
  if (/mac/i.test(p)) return "mac";
  if (/linux/i.test(p)) return "linux";
  return "";
}

/** The tips for this kind of computer, in order. */
export function boardHelpText(platform, canUsb = true) {
  const tips = [
    "Use a USB cable that can send data. Some cables only charge: try another one.",
    "Unplug the board, wait a few seconds, then plug it back in. Try another USB socket too.",
  ];
  const usb = canUsb ? " If it's still missing, press Try the USB way." : "";
  switch (platform) {
    case "windows":
      tips.push(
        "Clone boards (CH340 chip) and NodeMCUs (CP2102 chip) need a driver on Windows. Windows usually adds it by itself about a minute after you first plug the board in. If your board still isn't listed, ask your teacher or IT to install the CH340 or CP210x driver.",
        "Genuine Arduino boards, and ESP32-C3 or ESP32-S3 boards that plug straight into USB, need no driver." + usb);
      break;
    case "mac":
      tips.push("Macs already have the drivers for most boards (macOS 11 or newer)." + usb);
      break;
    case "chromeos":
      tips.push("Chromebooks already have the drivers for most boards." + usb);
      break;
    case "android":
      tips.push("On a tablet or phone, plug the board in with a USB-C or OTG adapter, then press Try the USB way.");
      break;
    case "linux":
      tips.push("Linux already has the drivers for most boards." + usb);
      break;
    default:
      tips.push("Your computer may need a driver for the board's USB chip (CH340 or CP2102). Ask your teacher." + usb);
  }
  if (canUsb) tips.push("The USB way talks to the board's USB chip straight from the browser, so it doesn't need a driver.");
  return tips;
}

/**
 * Shows the help. Returns a port id if the student connected their board
 * the USB way, else null.
 */
export async function boardHelp() {
  const buttons = [
    ...(usbSupported ? [{ id: "usb", label: "Try the USB way", default: true }] : []),
    { id: "close", label: "Close", cancel: true, default: !usbSupported },
  ];
  const pick = await messageBox({
    kind: "info",
    title: "Can't see your board?",
    instruction: "Can't see your board in the list?",
    text: boardHelpText(platformOf(), usbSupported),
    buttons,
  });
  if (pick !== "usb") return null;
  try {
    return await requestUsbPort();
  } catch (err) {
    await messageBox({ kind: "error", instruction: "The USB way didn't work.", text: err.message });
    return null;
  }
}
