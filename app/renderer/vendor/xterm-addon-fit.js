!function(e, t) {
    if ("object" == typeof exports && "object" == typeof module) {
        module.exports = t();
    } else if ("function" == typeof define && define.amd) {
        define([], t);
    } else if ("object" == typeof exports) {
        exports.FitAddon = t();
    } else {
        e.FitAddon = t();
    }
}(globalThis, (() => (() => {
    "use strict";
    
    var e = {};
    
    (() => {
        var t = e;
        Object.defineProperty(t, "__esModule", { value: !0 });
        t.FitAddon = void 0;
        
        t.FitAddon = class {
            activate(e) {
                this._terminal = e;
            }
            
            dispose() {}
            
            fit() {
                const e = this.proposeDimensions();
                if (!e || !this._terminal || isNaN(e.cols) || isNaN(e.rows)) return;
                
                const t = this._terminal._core;
                if (this._terminal.rows === e.rows && this._terminal.cols === e.cols) return;
                
                t._renderService.clear();
                this._terminal.resize(e.cols, e.rows);
            }
            
            proposeDimensions() {
                if (!this._terminal) return;
                if (!this._terminal.element || !this._terminal.element.parentElement) return;
                
                const e = this._terminal._core._renderService.dimensions;
                if (0 === e.css.cell.width || 0 === e.css.cell.height) return;
                
                const t = 0 === this._terminal.options.scrollback ? 0 : this._terminal.options.overviewRuler?.width || 14;
                const r = window.getComputedStyle(this._terminal.element.parentElement);
                const i = parseInt(r.getPropertyValue("height"));
                const o = Math.max(0, parseInt(r.getPropertyValue("width")));
                const s = window.getComputedStyle(this._terminal.element);
                const n = i - (parseInt(s.getPropertyValue("padding-top")) + parseInt(s.getPropertyValue("padding-bottom")));
                const l = o - (parseInt(s.getPropertyValue("padding-right")) + parseInt(s.getPropertyValue("padding-left"))) - t;
                
                return {
                    cols: Math.max(2, Math.floor(l / e.css.cell.width)),
                    rows: Math.max(1, Math.floor(n / e.css.cell.height))
                };
            }
        };
    })();
    
    return e;
})()));
//# sourceMappingURL=addon-fit.js.map
