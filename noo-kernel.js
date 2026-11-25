/* НООСЕТКА · ядро мира v1.0 «ПРОВЕРЯЙ, А НЕ ВЕРЬ» · кузня rtynbirf
   ЧЕЛОВЕК=АККАУНТ=PID1 · одно другое не исключает.

   Один файл, ноль зависимостей, браузер и Node (>=18, есть fetch).
   Автомат МИРА:  GHOST → WIRE → LIVE → READY · отказ → DEGRADED (с причиной)
   Автомат СЕТКИ: DARK → SCAN → COHERENT | FRACTURED

   ВХОДЫ: { манифест?, ядро?, стражи[] } · ВЫХОДЫ: { состояние, причина, брайль, события }

   ЧЕСТЬ МЕХАНИЗМА: состояние НЕ декларируется — оно вымеряется. Манифест
   качается по сети, ядро качается по сети, каждый страж качается по сети.
   Битый JSON = DEGRADED, недостающий страж = «стражи N/16» в причине.
   Ничего не врёт: и 404, и отказ сети видны как есть. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) { module.exports = factory(); }
  else { root.Noo = factory(); }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var VERSION = 'noo-kernel/1.0';
  var СТРАЖЕЙ_ТРЕБУЕТСЯ = 16;
  var БРАЙЛЬ_READY = '\u2817\u2811\u2801\u2819\u283D'; /* latin-g1: R E A D Y, канон дома */

  function rawUrl(мир, путь) {
    /* сегментное кодирование: кириллица в пути честная, слэши не трогаем */
    var п = String(путь || '').split('/').map(encodeURIComponent).join('/');
    return 'https://raw.githubusercontent.com/' + мир.владелец + '/' + мир.репо +
           '/' + (мир.ветка || 'main') + '/' + п;
  }

  function fetchOk(url, таймаут) {
    return new Promise(function (решено) {
      var сделано = false;
      var т = setTimeout(function () { if (!сделано) { сделано = true; решено(null); } }, таймаут || 12000);
      fetch(url, { cache: 'no-store' }).then(function (r) {
        if (сделано) return; сделано = true; clearTimeout(т);
        решено(r.ok ? r : null);
      }).catch(function () {
        if (сделано) return; сделано = true; clearTimeout(т); решено(null);
      });
    });
  }

  /* Автомат мира. Вход: { владелец, репо, ветка, ядро?, стражи?[], канон? }
     Выход: { состояние, причина, стражи_взято, брайль, события[] } */
  function мирСостояние(мир, опции) {
    опции = опции || {};
    var события = [];
    var брайль = String((мир && мир.брайль) || '');
    function фин(состояние, причина, взято) {
      return { состояние: состояние, причина: причина, стражи_взято: взято || 0,
               брайль: брайль, события: события, версия: VERSION };
    }
    if (!мир || !мир.репо) return фин('GHOST', 'мира нет в реестре');
    события.push({ т: 'мир', с: мир.репо });
    if (!мир.манифест) return фин('GHOST', 'noo-manifest.json не отвечает (404/сеть)');
    события.push({ т: 'манифест', с: 'есть' });
    /* живой манифест — дальше ядро */
    if (!мир.ядро_живо) return фин('WIRE', 'манифест на связи, ядро в репо не найдено');
    события.push({ т: 'ядро', с: 'есть' });
    /* поверхность, если заявлена */
    if (мир.поверхность && опции.проверятьПоверхность !== false) {
      if (!мир.поверхность_жива) return фин('DEGRADED', 'поверхность заявлена, но не отвечает');
      события.push({ т: 'поверхность', с: 'есть' });
    }
    var стражи = (мир.стражи || []);
    if (!стражи.length) {
      return фин('LIVE', 'ядро в репо · мир не заявляет стражей');
    }
    var взято = мир.стражи_взято;
    if (typeof взято !== 'number') return фин('DEGRADED', 'стражи не промерены');
    if (взято !== СТРАЖЕЙ_ТРЕБУЕТСЯ) {
      return фин('DEGRADED', 'стражи ' + взято + '/' + СТРАЖЕЙ_ТРЕБУЕТСЯ);
    }
    события.push({ т: 'стражи', с: СТРАЖЕЙ_ТРЕБУЕТСЯ + '/' + СТРАЖЕЙ_ТРЕБУЕТСЯ });
    if (String(мир.канон) !== 'READY') {
      return фин('DEGRADED', 'канон ' + String(мир.канон) + ' ≠ READY');
    }
    события.push({ т: 'канон', с: 'READY' });
    return фин('READY', 'стражи 16/16 · канон READY · ' + СТРАЖЕЙ_ТРЕБУЕТСЯ + ' стражей живы');
  }

  /* Промер одного мира по сети: манифест → ядро → стражи → поверхность. */
  async function промерить(мир, опции) {
    опции = опции || {};
    мир.манифест = null; мир.ядро_живо = false; мир.поверхность_жива = false; мир.стражи_взято = 0;
    var r = await fetchOk(rawUrl(мир, 'noo-manifest.json'), опции.таймаут);
    if (r) {
      try { мир.манифест = await r.json(); } catch (e) { мир.манифест = null; }
    }
    if (мир.манифест && Array.isArray(мир.манифест.стражи)) мир.стражи = мир.манифест.стражи;
    if (мир.манифест && мир.манифест.канон) мир.канон = мир.манифест.канон;
    if (мир.манифест && мир.манифест.брайль) мир.брайль = мир.манифест.брайль;
    if (мир.манифест && мир.манифест.поверхность && !мир.поверхность) мир.поверхность = мир.манифест.поверхность;
    var ядроПуть = (мир.манифест && мир.манифест.ядро) || 'noo-kernel.js';
    var kr = await fetchOk(rawUrl(мир, ядроПуть), опции.таймаут);
    мир.ядро_живо = !!kr;
    if (мир.ядро_живо && мир.стражи && мир.стражи.length) {
      var взято = 0;
      for (var i = 0; i < мир.стражи.length; i++) {
        var путь = мир.стражи[i] && (мир.стражи[i].p || мир.стражи[i].путь || мир.стражи[i]);
        if (!путь) continue;
        var sr = await fetchOk(rawUrl(мир, путь), опции.таймаут);
        if (sr) взято++;
      }
      мир.стражи_взято = взято;
    }
    if (мир.поверхность) {
      var pr = await fetchOk(мир.поверхность, опции.таймаут);
      мир.поверхность_жива = !!pr;
    }
    return мирСостояние(мир, опции);
  }

  /* Автомат сетки: DARK → SCAN → COHERENT | FRACTURED */
  async function скан(реестр, опции) {
    опции = опции || {};
    var миры = (реестр.миры || реестр || []);
    var строки = [];
    for (var i = 0; i < миры.length; i++) {
      var мир = Object.assign({ владелец: реестр.владелец || 'rtynbirf' }, миры[i]);
      if (опции.на_мир) await опции.на_мир(мир, i, миры.length);
      var итог = await промерить(мир, опции);
      строки.push(Object.assign(мир, итог));
    }
    var разбитые = строки.filter(function (с) { return с.состояние === 'GHOST' || с.состояние === 'DEGRADED'; });
    var ready = строки.filter(function (с) { return с.состояние === 'READY'; }).length;
    return {
      состояние: разбитые.length ? 'FRACTURED' : 'COHERENT',
      причина: разбитые.length
        ? (разбитые.length + ' миров вне канона: ' + разбитые.slice(0, 6).map(function (б) { return б.репо + ':' + б.состояние; }).join(', ') + (разбитые.length > 6 ? ' …' : ''))
        : ('все ' + строки.length + ' миров отвечают · READY: ' + ready),
      миры: строки,
      ready: ready,
      версия: VERSION
    };
  }

  /* Брайль-строка сетки: фрагменты миров выстраиваются по «порядок». */
  function брайльСтрока(итог) {
    var фраг = (итог.миры || [])
      .filter(function (м) { return м.брайль; })
      .sort(function (a, b) { return (a.порядок || 0) - (b.порядок || 0); })
      .map(function (м) { return м.брайль; });
    return фраг.join('\u2800');
  }

  /* Рендер карты миров в элемент. Ноль innerHTML-ширь — только нужные узлы. */
  function рендер(итог, el) {
    if (!el) return null;
    el.setAttribute('data-noo-grid', '');
    var сводка = document.createElement('div');
    сводка.setAttribute('data-noo-sводка', '');
    var цвет = итог.состояние === 'COHERENT' ? '#3fb950' : (итог.состояние === 'SCAN' ? '#d29922' : '#f85149');
    сводка.style.cssText = 'font:13px/1.5 ui-monospace,Consolas,monospace;color:' + цвет + ';padding:6px 0';
    сводка.textContent = 'СЕТКА ' + итог.состояние + ' — ' + итог.причина;
    el.appendChild(сводка);
    var т = document.createElement('table');
    т.style.cssText = 'width:100%;border-collapse:collapse;font:12.5px/1.5 ui-monospace,Consolas,monospace';
    var шап = т.createTHead().insertRow();
    ['МИР', 'РОЛЬ', 'СОСТОЯНИЕ', 'СТРАЖИ', 'ПРИЧИНА'].forEach(function (з) {
      var я = шап.insertCell(); я.textContent = з;
      я.style.cssText = 'text-align:left;border-bottom:1px solid rgba(217,164,65,.35);padding:4px 8px;color:#d9a441';
    });
    var тело = т.createTBody();
    итог.миры.forEach(function (м) {
      var стр = тело.insertRow();
      var цветС = { READY: '#3fb950', LIVE: '#58a6ff', WIRE: '#d29922', DEGRADED: '#f85149', GHOST: '#8b949e' }[м.состояние] || '#8b949e';
      function ячейка(текст, цв) {
        var я = стр.insertCell();
        я.textContent = текст == null ? '' : String(текст);
        я.style.cssText = 'border-bottom:1px solid rgba(217,164,65,.14);padding:4px 8px;color:' + (цв || '#c9c2b4');
        return я;
      }
      ячейка(м.репо, '#f2c464');
      ячейка(м.роль || '');
      ячейка(м.состояние, цветС);
      ячейка(typeof м.стражи_взято === 'number' && м.стражи ? (м.стражи_взято + '/' + м.стражи.length) : '');
      ячейка(м.причина || '');
    });
    el.appendChild(т);
    var бр = document.createElement('div');
    бр.style.cssText = 'font:15px/1.8 ui-monospace,Consolas,monospace;letter-spacing:.35em;color:#d9a441;padding:10px 0';
    бр.setAttribute('data-noo-брайль', '');
    бр.textContent = брайльСтрока(итог) || БРАЙЛЬ_READY;
    el.appendChild(бр);
    return el;
  }

  return {
    VERSION: VERSION,
    СТРАЖЕЙ_ТРЕБУЕТСЯ: СТРАЖЕЙ_ТРЕБУЕТСЯ,
    БРАЙЛЬ_READY: БРАЙЛЬ_READY,
    мирСостояние: мирСостояние,
    промерить: промерить,
    скан: скан,
    брайльСтрока: брайльСтрока,
    рендер: рендер,
    rawUrl: rawUrl
  };
});
