/* Mavie TV — ES2018 / ES5-Safe 2D Spatial Navigation & Back Stack Engine
 * Handles D-Pad Arrow keys, Enter/OK, Tizen Back (10009), LG webOS Back (461),
 * Escape (27), media keys, channel zapping, and Samsung Seller Office Exit flow.
 */
(function (root) {
  'use strict';

  var KEYS = {
    LEFT: 37,
    UP: 38,
    RIGHT: 39,
    DOWN: 40,
    ENTER: 13,
    ESC: 27,
    BACKSPACE: 8,
    TIZEN_BACK: 10009,
    WEBOS_BACK: 461,
    MEDIA_PLAY_PAUSE: 10252,
    MEDIA_PLAY: 415,
    MEDIA_PAUSE: 19,
    MEDIA_STOP: 413,
    MEDIA_REWIND: 412,
    MEDIA_FF: 417,
    CHANNEL_UP: 427,
    CHANNEL_DOWN: 428,
    COLOR_RED: 403,
    COLOR_GREEN: 404,
    COLOR_YELLOW: 405,
    COLOR_BLUE: 406
  };

  function isBackKey(keyCode, keyName) {
    if (keyCode === KEYS.TIZEN_BACK || keyCode === KEYS.WEBOS_BACK || keyCode === KEYS.ESC) {
      return true;
    }
    if (keyName === 'Escape' || keyName === 'Back' || keyName === 'GoBack' || keyName === 'XF86Back') {
      return true;
    }
    return false;
  }

  function findBestCandidate(originRect, candidates, direction) {
    var ox = originRect.left + originRect.width / 2;
    var oy = originRect.top + originRect.height / 2;
    var best = null;
    var bestScore = Infinity;
    var i, item, rect, cx, cy, dx, dy, primary, secondary, score;

    for (i = 0; i < candidates.length; i++) {
      item = candidates[i];
      rect = item.rect;
      if (!rect || rect.width <= 0 || rect.height <= 0) continue;
      cx = rect.left + rect.width / 2;
      cy = rect.top + rect.height / 2;
      dx = cx - ox;
      dy = cy - oy;

      if (direction === 'left' && dx >= -4) continue;
      if (direction === 'right' && dx <= 4) continue;
      if (direction === 'up' && dy >= -4) continue;
      if (direction === 'down' && dy <= 4) continue;

      if (direction === 'left' || direction === 'right') {
        primary = Math.abs(dx);
        secondary = Math.abs(dy);
        // Prefer elements whose vertical spans overlap the origin
        var vOverlap = !(rect.bottom < originRect.top || rect.top > originRect.bottom);
        score = primary + secondary * (vOverlap ? 1.35 : 3.2);
      } else {
        primary = Math.abs(dy);
        secondary = Math.abs(dx);
        var hOverlap = !(rect.right < originRect.left || rect.left > originRect.right);
        score = primary + secondary * (hOverlap ? 1.35 : 2.8);
      }

      if (score < bestScore) {
        bestScore = score;
        best = item.el;
      }
    }
    return best;
  }

  function createBackStack(onRootBack) {
    var stack = [];
    return {
      push: function (handler) {
        if (typeof handler === 'function') {
          stack.push(handler);
        }
      },
      pop: function () {
        if (stack.length > 0) {
          return stack.pop();
        }
        return null;
      },
      clear: function () {
        stack.length = 0;
      },
      size: function () {
        return stack.length;
      },
      triggerBack: function () {
        while (stack.length > 0) {
          var fn = stack.pop();
          if (typeof fn === 'function') {
            var handled = fn();
            if (handled !== false) return 'popped';
          }
        }
        if (typeof onRootBack === 'function') {
          onRootBack();
          return 'root';
        }
        return 'none';
      }
    };
  }

  function isElementVisible(el) {
    if (!el || el.disabled) return false;
    var node = el;
    while (node && node.nodeType === 1) {
      if (node.hidden || node.getAttribute('hidden') !== null) return false;
      var style = root.getComputedStyle ? root.getComputedStyle(node) : null;
      if (style && (style.display === 'none' || style.visibility === 'hidden')) return false;
      node = node.parentNode;
    }
    var r = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
    return !!(r && r.width > 0 && r.height > 0);
  }

  function scrollIntoCenter(el) {
    if (!el || !el.parentNode) return;
    var parent = el.parentNode;
    while (parent && parent !== document.body && parent.nodeType === 1) {
      var st = root.getComputedStyle ? root.getComputedStyle(parent) : null;
      if (st) {
        if ((st.overflowX === 'auto' || st.overflowX === 'scroll') && parent.scrollWidth > parent.clientWidth) {
          var pRect = parent.getBoundingClientRect();
          var eRect = el.getBoundingClientRect();
          var deltaX = (eRect.left + eRect.width / 2) - (pRect.left + pRect.width / 2);
          parent.scrollLeft = Math.max(0, parent.scrollLeft + deltaX);
        }
        if ((st.overflowY === 'auto' || st.overflowY === 'scroll') && parent.scrollHeight > parent.clientHeight) {
          var pRectY = parent.getBoundingClientRect();
          var eRectY = el.getBoundingClientRect();
          var deltaY = (eRectY.top + eRectY.height / 2) - (pRectY.top + pRectY.height / 2);
          parent.scrollTop = Math.max(0, parent.scrollTop + deltaY);
        }
      }
      parent = parent.parentNode;
    }
  }

  var state = {
    current: null,
    scopeRoot: null,
    mediaHandler: null,
    backStack: null,
    initialized: false
  };

  function getActiveScope() {
    if (state.scopeRoot && isElementVisible(state.scopeRoot)) {
      return state.scopeRoot;
    }
    if (typeof document === 'undefined') return null;
    // Automatically prioritize open overlays/modals/player
    var priorityIds = ['tvPlayerLayer', 'tvExitModal', 'tvPairModal', 'tvDetailModal'];
    var i, layer;
    for (i = 0; i < priorityIds.length; i++) {
      layer = document.getElementById(priorityIds[i]);
      if (layer && !layer.hidden) return layer;
    }
    return document.getElementById('tvApp') || document.body;
  }

  function getFocusables(scope) {
    if (!scope || !scope.querySelectorAll) return [];
    var raw = scope.querySelectorAll('[data-tv-focusable="true"]');
    var out = [];
    var i;
    for (i = 0; i < raw.length; i++) {
      if (isElementVisible(raw[i])) out.push(raw[i]);
    }
    return out;
  }

  function focusElement(el) {
    if (!el) return false;
    if (state.current && state.current !== el && state.current.classList) {
      state.current.classList.remove('tv-focused');
    }
    state.current = el;
    if (el.classList) {
      el.classList.add('tv-focused');
    }
    if (typeof el.focus === 'function') {
      try {
        el.focus();
      } catch (err) {
        // Ignore non-focusable browser quirks
      }
    }
    scrollIntoCenter(el);
    return true;
  }

  function focusFirst(scope) {
    var rootEl = scope || getActiveScope();
    var list = getFocusables(rootEl);
    if (list.length > 0) {
      return focusElement(list[0]);
    }
    return false;
  }

  function move(direction) {
    var scope = getActiveScope();
    var list = getFocusables(scope);
    if (list.length === 0) return false;

    if (!state.current || !isElementVisible(state.current) || list.indexOf(state.current) === -1) {
      return focusElement(list[0]);
    }

    // Optional explicit directional hint attribute
    var hintAttr = 'data-tv-' + direction;
    var hintId = state.current.getAttribute ? state.current.getAttribute(hintAttr) : null;
    if (hintId && typeof document !== 'undefined') {
      var hinted = document.getElementById(hintId);
      if (hinted && isElementVisible(hinted)) {
        return focusElement(hinted);
      }
    }

    var originRect = state.current.getBoundingClientRect();
    var candidates = [];
    var i, el;
    for (i = 0; i < list.length; i++) {
      el = list[i];
      if (el === state.current) continue;
      candidates.push({ el: el, rect: el.getBoundingClientRect() });
    }

    var next = findBestCandidate(originRect, candidates, direction);
    if (next) {
      return focusElement(next);
    }
    return false;
  }

  function init(options) {
    var opts = options || {};
    state.backStack = createBackStack(opts.onRootBack);
    state.mediaHandler = opts.onMediaKey || null;

    if (state.initialized || typeof document === 'undefined') return;
    state.initialized = true;

    document.addEventListener('keydown', function (event) {
      var code = event.keyCode || event.which || 0;
      var key = event.key || '';
      var activeTag = document.activeElement ? document.activeElement.tagName : '';
      var inTextField = (activeTag === 'INPUT' || activeTag === 'TEXTAREA');

      if (isBackKey(code, key) || (code === KEYS.BACKSPACE && !inTextField)) {
        event.preventDefault();
        state.backStack.triggerBack();
        return;
      }

      // Forward TV media & channel keys
      if (
        code === KEYS.MEDIA_PLAY_PAUSE ||
        code === KEYS.MEDIA_PLAY ||
        code === KEYS.MEDIA_PAUSE ||
        code === KEYS.MEDIA_STOP ||
        code === KEYS.MEDIA_REWIND ||
        code === KEYS.MEDIA_FF ||
        code === KEYS.CHANNEL_UP ||
        code === KEYS.CHANNEL_DOWN ||
        code === KEYS.COLOR_RED ||
        code === KEYS.COLOR_GREEN ||
        code === KEYS.COLOR_YELLOW ||
        code === KEYS.COLOR_BLUE
      ) {
        if (typeof state.mediaHandler === 'function') {
          var consumed = state.mediaHandler(code, event);
          if (consumed) {
            event.preventDefault();
            return;
          }
        }
      }

      // Let left/right move cursor inside focused text inputs unless user moves up/down
      if (inTextField && (code === KEYS.LEFT || code === KEYS.RIGHT)) {
        return;
      }

      if (code === KEYS.LEFT) {
        event.preventDefault();
        move('left');
      } else if (code === KEYS.RIGHT) {
        event.preventDefault();
        move('right');
      } else if (code === KEYS.UP) {
        event.preventDefault();
        move('up');
      } else if (code === KEYS.DOWN) {
        event.preventDefault();
        move('down');
      } else if (code === KEYS.ENTER) {
        if (state.current && !inTextField) {
          event.preventDefault();
          if (typeof state.current.click === 'function') {
            state.current.click();
          }
        }
      }
    });

    document.addEventListener('mouseover', function (event) {
      var node = event.target;
      while (node && node !== document.body && node.nodeType === 1) {
        if (node.getAttribute && node.getAttribute('data-tv-focusable') === 'true') {
          if (isElementVisible(node)) {
            focusElement(node);
          }
          break;
        }
        node = node.parentNode;
      }
    });
  }

  var api = {
    KEYS: KEYS,
    isBackKey: isBackKey,
    findBestCandidate: findBestCandidate,
    createBackStack: createBackStack,
    init: init,
    move: move,
    focusElement: focusElement,
    focusFirst: focusFirst,
    setScope: function (el) { state.scopeRoot = el || null; },
    getCurrent: function () { return state.current; },
    pushBack: function (fn) { if (state.backStack) state.backStack.push(fn); },
    popBack: function () { return state.backStack ? state.backStack.pop() : null; },
    triggerBack: function () { return state.backStack ? state.backStack.triggerBack() : 'none'; }
  };

  root.MavieSpatial = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : this);
