/**
 * rs-settings-vacation – Vacation mode settings.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";
import { toDisplay, toCelsius, tempUnit, tempStep, tempRange } from "../../utils/temperature";

@customElement("rs-settings-vacation")
export class RsSettingsVacation extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public vacationActive = false;
  @property({ type: Number }) public vacationTemp = 15;
  @property({ type: String }) public vacationUntil = "";

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
          <span class="toggle-label">${localize("vacation.title", l)}</span>
          <span class="toggle-hint">${localize("vacation.hint", l)}</span>
        </div>
        <ha-switch
          .checked=${this.vacationActive}
          @change=${(e: Event) => {
            const active = (e.target as HTMLInputElement).checked;
            this._fire("vacationActive", active);
            if (!active) this._fire("vacationUntil", "");
          }}
        ></ha-switch>
      </div>

      ${this.vacationActive
        ? html`
            <div class="threshold-grid" style="margin-top: 12px">
              <div class="threshold-field">
                <ha-textfield
                  .value=${this.vacationUntil}
                  .label=${localize("vacation.end_date", l)}
                  type="datetime-local"
                  @change=${(e: Event) => this._fire("vacationUntil", (e.target as HTMLInputElement).value)}
                ></ha-textfield>
              </div>
              <div class="threshold-field">
                <ha-textfield
                  .value=${String(toDisplay(this.vacationTemp, this.hass))}
                  .label=${localize("vacation.setback_temp", l)}
                  .suffix=${tempUnit(this.hass)}
                  type="number"
                  step=${tempStep(this.hass)}
                  min=${tempRange(5, 25, this.hass).min}
                  max=${tempRange(5, 25, this.hass).max}
                  @change=${(e: Event) => {
                    const v = parseFloat((e.target as HTMLInputElement).value);
                    if (!isNaN(v)) this._fire("vacationTemp", toCelsius(v, this.hass));
                  }}
                ></ha-textfield>
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

    @media (max-width: 600px) {
      .threshold-grid { grid-template-columns: 1fr; }
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-vacation": RsSettingsVacation;
  }
}
