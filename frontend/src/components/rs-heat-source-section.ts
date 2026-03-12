import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { HomeAssistant } from "../types";
import { localize } from "../utils/localize";

import "./shared/rs-toggle-row";
import "./shared/rs-threshold-field";

@customElement("rs-heat-source-section")
export class RsHeatSourceSection extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public enabled = false;
  @property({ type: Number }) public primaryDelta = 1.5;
  @property({ type: Number }) public outdoorThreshold = 5.0;
  @property({ type: Number }) public acMinOutdoor = -15.0;

  static styles = css`
    :host {
      display: block;
    }

    .settings {
      display: flex;
      flex-direction: column;
      gap: 16px;
      padding: 0 16px 16px;
    }
  `;

  render() {
    const lang = this.hass.language;

    return html`
      <rs-toggle-row
        .label=${localize("heat_source.toggle", lang)}
        .hint=${localize("heat_source.toggle_hint", lang)}
        .checked=${this.enabled}
        @toggle-changed=${this._onToggle}
      ></rs-toggle-row>

      ${this.enabled
        ? html`
            <div class="settings">
              <rs-threshold-field
                .label=${localize("heat_source.primary_delta", lang)}
                .suffix=${localize("heat_source.primary_delta_suffix", lang)}
                .hint=${localize("heat_source.primary_delta_hint", lang)}
                .value=${this.primaryDelta}
                .min=${0.5}
                .max=${5.0}
                .step=${0.1}
                @value-changed=${(e: CustomEvent<number>) =>
                  this._emit("heat_source_primary_delta", e.detail)}
              ></rs-threshold-field>

              <rs-threshold-field
                .label=${localize("heat_source.outdoor_threshold", lang)}
                .suffix=${localize("heat_source.outdoor_threshold_suffix", lang)}
                .hint=${localize("heat_source.outdoor_threshold_hint", lang)}
                .value=${this.outdoorThreshold}
                .min=${-20}
                .max=${25}
                .step=${1}
                @value-changed=${(e: CustomEvent<number>) =>
                  this._emit("heat_source_outdoor_threshold", e.detail)}
              ></rs-threshold-field>

              <rs-threshold-field
                .label=${localize("heat_source.ac_min_outdoor", lang)}
                .suffix=${localize("heat_source.ac_min_outdoor_suffix", lang)}
                .hint=${localize("heat_source.ac_min_outdoor_hint", lang)}
                .value=${this.acMinOutdoor}
                .min=${-30}
                .max=${5}
                .step=${1}
                @value-changed=${(e: CustomEvent<number>) =>
                  this._emit("heat_source_ac_min_outdoor", e.detail)}
              ></rs-threshold-field>
            </div>
          `
        : nothing}
    `;
  }

  private _onToggle(e: CustomEvent<boolean>) {
    this._emit("heat_source_orchestration", e.detail);
  }

  private _emit(key: string, value: unknown) {
    this.dispatchEvent(
      new CustomEvent("setting-changed", {
        detail: { key, value },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-heat-source-section": RsHeatSourceSection;
  }
}
