import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

@customElement("rs-toggle-row")
export class RsToggleRow extends LitElement {
  @property({ type: String }) public label = "";
  @property({ type: String }) public hint = "";
  @property({ type: Boolean }) public checked = false;
  @property({ type: Boolean }) public disabled = false;

  static styles = css`
    :host {
      display: block;
    }

    .toggle-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
    }

    .toggle-text {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .toggle-label {
      font-weight: 500;
    }

    .toggle-hint {
      font-size: 13px;
      color: var(--secondary-text-color);
    }
  `;

  render() {
    return html`
      <div class="toggle-row">
        <div class="toggle-text">
          <span class="toggle-label">${this.label}</span>
          ${this.hint
            ? html`<span class="toggle-hint">${this.hint}</span>`
            : nothing}
        </div>
        <ha-switch
          .checked=${this.checked}
          .disabled=${this.disabled}
          @change=${this._onToggle}
        ></ha-switch>
      </div>
    `;
  }

  private _onToggle(e: Event) {
    this.dispatchEvent(
      new CustomEvent("toggle-changed", {
        detail: (e.target as HTMLInputElement).checked,
        bubbles: true,
        composed: true,
      })
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-toggle-row": RsToggleRow;
  }
}
