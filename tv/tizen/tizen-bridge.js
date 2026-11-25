/* Mavie TV — Samsung Tizen 5.5+ (TU8500) Platform Bridge
 * Pure ES2018 / ES5-safe. Registers remote media/channel/color keys via
 * tizen.tvinputdevice.registerKeyBatch.
 * IMPORTANT: Intentionally does NOT register 'Exit' (10182) so Tizen handles
 * the physical Exit button natively per Samsung Seller Office QA guidelines.
 */
(function (root) {
  'use strict';

  var MEDIA_KEYS = [
    'MediaPlayPause',
    'MediaPlay',
    'MediaPause',
    'MediaStop',
    'MediaRewind',
    'MediaFastForward',
    'ChannelUp',
    'ChannelDown',
    'ColorF0Red',
    'ColorF1Green',
    'ColorF2Yellow',
    'ColorF3Blue'
  ];

  function registerKeys() {
    try {
      if (root.tizen && root.tizen.tvinputdevice && root.tizen.tvinputdevice.registerKeyBatch) {
        root.tizen.tvinputdevice.registerKeyBatch(MEDIA_KEYS);
      }
    } catch (err) {
      // Fallback for non-Tizen browser previews
    }
  }

  function setScreenSaver(enabled) {
    try {
      if (root.webapis && root.webapis.appcommon && root.webapis.appcommon.setScreenSaver) {
        var states = root.webapis.appcommon.AppCommonScreenSaverState;
        root.webapis.appcommon.setScreenSaver(enabled ? states.SCREEN_SAVER_ON : states.SCREEN_SAVER_OFF);
      }
    } catch (err) {
      // Optional on emulators / non-Tizen runtimes
    }
  }

  function exitApp() {
    try {
      if (root.tizen && root.tizen.application && root.tizen.application.getCurrentApplication) {
        root.tizen.application.getCurrentApplication().exit();
      }
    } catch (err) {
      // Ignore outside Tizen
    }
  }

  registerKeys();

  root.MaviePlatform = {
    name: 'tizen',
    label: 'Samsung Tizen TV (5.5+)',
    backKeyCode: 10009,
    mediaKeys: MEDIA_KEYS.slice(),
    setScreenSaver: setScreenSaver,
    exitApp: exitApp
  };
})(typeof window !== 'undefined' ? window : this);
