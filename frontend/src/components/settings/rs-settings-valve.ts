/**
 * rs-settings-valve – Valve protection settings.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";

@customElement("rs-settings-valve")
export class RsSettingsValve extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public valveProtectionEnabled = false;
  @property({ type: Number }) public valveProtectionInterval = 7;

  private _fire(key: string, value: unknown) {
    this.dispatchEvent(new CustomEvent("setting-changed", {
      detail: { key, value },
      bubbles: true,
      composed: true,
    }));
  }

  render() {
    const l = this.hass.language;

    return html`
      <div class="toggle-row">
        <div class="toggle-text">
          <span class="toggle-label">${localize("valve_protection.title", l)}</span>
          <span class="toggle-hint">${localize("valve_protection.hint", l)}</span>
        </div>
        <ha-switch
          .checked=${this.valveProtectionEnabled}
          @change=${(e: Event) => this._fire("valveProtectionEnabled", (e.target as HTMLInputElement).checked)}
        ></ha-switch>
      </div>

      ${this.valveProtectionEnabled
        ? html`
            <div class="threshold-grid" style="margin-top: 12px">
              <div class="threshold-field">
                <ha-textfield
                  .value=${String(this.valveProtectionInterval)}
                  .label=${localize("valve_protection.interval_label", l)}
                  .suffix=${localize("valve_protection.interval_suffix", l)}
                  type="number" step="1" min="1" max="90"
                  @change=${(e: Event) => {
                    const v = parseInt((e.target as HTMLInputElement).value, 10);
                    if (!isNaN(v) && v >= 1 && v <= 90) this._fire("valveProtectionInterval", v);
                  }}
                ></ha-textfield>
                <span class="field-hint">${localize("valve_protection.interval_hint", l)}</span>
              </div>
            </div>
          `
        : nothing}
    `;
  }

  static styles = css`
    :host { display: block; }

    .toggle-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
    .toggle-text { display: flex; flex-direction: column; gap: 4px; flex: 1; }
    .toggle-label { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
    .toggle-hint { font-size: 13px; color: var(--secondary-text-color); line-height: 1.4; }

    .threshold-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .threshold-field { display: flex; flex-direction: column; gap: 4px; }
    .threshold-field ha-textfield { width: 100%; }
    .field-hint { color: var(--secondary-text-color); font-size: 12px; }

    @media (max-width: 600px) {
      .threshold-grid { grid-template-columns: 1fr; }
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-valve": RsSettingsValve;
  }
}
