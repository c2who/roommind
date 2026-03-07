/**
 * rs-settings-general – General settings: climate control, display options.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../../types";
import { localize } from "../../utils/localize";

@customElement("rs-settings-general")
export class RsSettingsGeneral extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public groupByFloor = false;
  @property({ type: Boolean }) public climateControlActive = true;

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
      ${this.hass.floors && Object.keys(this.hass.floors).length > 0
        ? html`<div class="settings-section first">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">${localize("settings.group_by_floor", l)}</span>
              </div>
              <ha-switch
                .checked=${this.groupByFloor}
                @change=${(e: Event) => this._fire("groupByFloor", (e.target as HTMLInputElement).checked)}
              ></ha-switch>
            </div>
          </div>`
        : nothing}

      <div class="settings-section ${this.hass.floors && Object.keys(this.hass.floors).length > 0 ? "" : "first"}">
        <div class="toggle-row">
          <div class="toggle-text">
            <span class="toggle-label">${localize("settings.climate_control_active", l)}</span>
            <span class="toggle-hint">${localize("settings.climate_control_hint", l)}</span>
          </div>
          <ha-switch
            .checked=${this.climateControlActive}
            @change=${(e: Event) => this._fire("climateControlActive", (e.target as HTMLInputElement).checked)}
          ></ha-switch>
        </div>
      </div>
    `;
  }

  static styles = css`
    :host { display: block; }

    .settings-section { padding: 16px 0; border-top: 1px solid var(--divider-color); }
    .settings-section:first-child, .settings-section.first { border-top: none; padding-top: 0; }

    .toggle-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
    .toggle-text { display: flex; flex-direction: column; gap: 4px; flex: 1; }
    .toggle-label { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
    .toggle-hint { font-size: 13px; color: var(--secondary-text-color); line-height: 1.4; }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-general": RsSettingsGeneral;
  }
}
