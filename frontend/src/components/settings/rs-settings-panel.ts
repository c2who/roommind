/**
 * rs-settings-panel – Reusable accordion panel for settings sections.
 * Wraps ha-expansion-panel with icon, title, optional badge, and intro text.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

@customElement("rs-settings-panel")
export class RsSettingsPanel extends LitElement {
  @property({ type: String }) public icon = "";
  @property({ type: String }) public heading = "";
  @property({ type: String }) public intro = "";
  @property({ type: String }) public badge = "";
  @property({ type: String }) public badgeHint = "";

  render() {
    return html`
      <ha-expansion-panel outlined>
        <div slot="header" class="panel-header">
          <ha-icon .icon=${this.icon}></ha-icon>
          <span>${this.heading}</span>
          ${this.badge
            ? html`<span class="badge" title=${this.badgeHint}>${this.badge}</span>`
            : nothing}
        </div>
        <div class="panel-content">
          ${this.intro
            ? html`<p class="section-intro">${this.intro}</p>`
            : nothing}
          <slot></slot>
        </div>
      </ha-expansion-panel>
    `;
  }

  static styles = css`
    :host { display: block; }

    .panel-header {
      display: flex;
      align-items: center;
      gap: 10px;
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
    }

    .panel-header span {
      color: var(--primary-text-color);
      font-weight: 500;
    }

    .badge {
      font-size: 10px;
      font-weight: 600;
      color: var(--primary-color);
      background: color-mix(in srgb, var(--primary-color) 12%, transparent);
      padding: 2px 6px;
      border-radius: 4px;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      cursor: default;
    }

    .panel-content {
      padding: 16px 16px 16px;
    }

    .section-intro {
      color: var(--secondary-text-color);
      font-size: 13px; line-height: 1.5;
      margin: 0 0 16px;
      padding: 2px 0 2px 12px;
      border-left: 3px solid var(--divider-color);
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-panel": RsSettingsPanel;
  }
}
