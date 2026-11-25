/* Mavie TV — LG webOS 4.0+ Platform Bridge
 * Pure ES2018 / ES5-safe. Maps webOS Back key (461), lifecycle, and clean exit.
 */
(function (root) {
  'use strict';

  function setScreenSaver(enabled) {
    try {
      if (root.webOSSystem && typeof root.webOSSystem.setKeepAlive === 'function') {
        root.webOSSystem.setKeepAlive(!enabled);
      }
    } catch (err) {
      // Optional on older webOS builds
    }
  }

  function exitApp() {
    try {
      if (root.webOSSystem && typeof root.webOSSystem.close === 'function') {
        root.webOSSystem.close();
        return;
      }
      if (root.PalmSystem && typeof root.PalmSystem.deactivate === 'function') {
        root.PalmSystem.deactivate();
        return;
      }
      if (typeof root.close === 'function') {
        root.close();
      }
    } catch (err) {
      // Ignore outside webOS
    }
  }

  root.MaviePlatform = {
    name: 'webos',
    label: 'LG webOS Smart TV',
    backKeyCode: 461,
    setScreenSaver: setScreenSaver,
    exitApp: exitApp
  };
})(typeof window !== 'undefined' ? window : this);
