import { LitElement, html, css, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  HomeAssistant,
  HassArea,
  RoomConfig,
  ClimateMode,
  ScheduleEntry,
  PassiveDevice,
  CoverScheduleEntry,
} from "../types";
import "./rs-hero-status";
import "./rs-climate-mode-selector";
import "./rs-schedule-settings";
import "./rs-device-section";
import "./rs-section-card";
import "./rs-override-section";
import "./rs-presence-section";
import "./rs-covers-section";
import "./rs-heat-source-section";
import "../components/shared/rs-toggle-row";
import { localize } from "../utils/localize";
import { fireSaveStatus } from "../utils/events";
import type { RsOverrideSection } from "./rs-override-section";

@customElement("rs-room-detail")
export class RsRoomDetail extends LitElement {
  @property({ attribute: false }) public area!: HassArea;
  @property({ attribute: false }) public config: RoomConfig | null = null;
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean }) public presenceEnabled = false;
  @property({ attribute: false }) public presencePersons: string[] = [];
  @property({ type: Boolean }) public climateControlActive = true;

  @property({ type: Boolean }) public valveProtectionEnabled = false;

  @state() private _selectedThermostats: Set<string> = new Set();
  @state() private _selectedAcs: Set<string> = new Set();
  @state() private _entityModes: Record<string, "auto" | "heat_only" | "cool_only"> = {};
  @state() private _selectedTempSensor = "";
  @state() private _selectedHumiditySensor = "";
  @state() private _selectedWindowSensors: Set<string> = new Set();
  @state() private _windowOpenDelay = 0;
  @state() private _windowCloseDelay = 0;
  @state() private _climateMode: ClimateMode = "auto";
  @state() private _schedules: ScheduleEntry[] = [];
  @state() private _scheduleSelectorEntity = "";
  @state() private _comfortHeat = 21.0;
  @state() private _comfortCool = 24.0;
  @state() private _ecoHeat = 17.0;
  @state() private _ecoCool = 27.0;
  @state() private _error = "";
  @state() private _dirty = false;
  @state() private _editingSchedule = false;
  @state() private _editingDevices = false;
  @state() private _editingPresence = false;
  @state() private _selectedPresencePersons: string[] = [];
  @state() private _displayName = "";
  @state() private _heatingSystemType = "";
  @state() private _passiveDevices: PassiveDevice[] = [];
  @state() private _editingPassiveDevices = false;
  @state() private _selectedCovers: Set<string> = new Set();
  @state() private _coversAutoEnabled = false;
  @state() private _coversDeployThreshold = 1.5;
  @state() private _coversMinPosition = 0;
  @state() private _coversOverrideMinutes = 60;
  @state() private _coverSchedules: CoverScheduleEntry[] = [];
  @state() private _coverScheduleSelectorEntity = "";
  @state() private _coversNightClose = false;
  @state() private _coversNightPosition = 0;
  @state() private _coversSensorOnly = false;
  @state() private _editingCovers = false;
  @state() private _isOutdoor = false;
  @state() private _valveProtectionExclude: Set<string> = new Set();
  @state() private _heatSourceOrchestration = false;
  @state() private _heatSourcePrimaryDelta = 1.5;
  @state() private _heatSourceOutdoorThreshold = 5.0;
  @state() private _heatSourceAcMinOutdoor = -15.0;

  private _prevAreaId: string | null = null;
  private _saveDebounce?: ReturnType<typeof setTimeout>;

  static styles = css`
    :host {
      display: block;
      max-width: 1100px;
      margin: 0 auto;
    }

    .detail-layout {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      align-items: start;
    }

    .col-left,
    .col-right {
      display: flex;
      flex-direction: column;
      gap: 16px;
      min-width: 0;
    }

    @media (max-width: 860px) {
      .detail-layout {
        grid-template-columns: 1fr;
      }
    }

    .outdoor-toggle-card {
      padding: 12px 16px;
    }

    /* Section cards handled by rs-section-card */

    /* YAML code block for info panels (slotted into rs-section-card) */
    .yaml-block {
      background: var(--primary-background-color, #f5f5f5);
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 6px;
      padding: 10px 14px;
      margin: 8px 0;
      font-family: var(--code-font-family, monospace);
      font-size: 12px;
      line-height: 1.6;
      white-space: pre;
      overflow-x: auto;
      color: var(--primary-text-color);
    }
    .yaml-key {
      color: #0550ae;
    }
    .yaml-value {
      color: #0a3069;
    }

    /* Actions */
    .actions {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 8px;
      margin-bottom: 24px;
    }

    .error {
      color: var(--error-color, #d32f2f);
      font-size: 13px;
      margin-top: 8px;
    }

    .field-hint {
      color: var(--secondary-text-color);
      font-size: 12px;
    }

    .exceptions-link {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: none;
      border: none;
      padding: 8px 0 0;
      margin: 0;
      cursor: pointer;
      font-size: 13px;
      color: var(--primary-color);
      font-family: inherit;
    }

    .exceptions-link:hover {
      text-decoration: underline;
    }
    .passive-device-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 14px;
      font-size: 14px;
      color: var(--primary-text-color);
      border-radius: 10px;
      margin-bottom: 2px;
      transition: background 0.15s;
    }

    .passive-device-row:hover {
      background: rgba(0, 0, 0, 0.02);
    }

    .passive-device-info {
      flex: 1;
      min-width: 0;
    }

    .passive-device-name {
      font-size: 14px;
      font-weight: 450;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .passive-device-entity {
      font-family: var(--code-font-family, monospace);
      font-size: 11px;
      color: var(--secondary-text-color);
      margin-top: 2px;
      opacity: 0.7;
    }

    .passive-mode-badge {
      display: inline-flex;
      align-items: center;
      font-size: 10px;
      font-weight: 500;
      color: var(--primary-color);
      background: rgba(3, 169, 244, 0.1);
      padding: 2px 8px;
      border-radius: 10px;
      letter-spacing: 0.3px;
      flex-shrink: 0;
    }

    .passive-selects {
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex-shrink: 0;
    }

    .passive-select {
      flex-shrink: 0;
      --ha-select-min-width: 120px;
    }

    .passive-pf-field {
      --ha-select-min-width: 80px;
      width: 80px;
    }

    .passive-remove-btn {
      background: none;
      border: none;
      padding: 4px;
      cursor: pointer;
      color: var(--secondary-text-color);
      border-radius: 4px;
      display: flex;
      align-items: center;
      flex-shrink: 0;
    }

    .passive-remove-btn:hover {
      color: var(--error-color, #d32f2f);
      background: rgba(211, 47, 47, 0.06);
    }

    .passive-entity-picker-wrap {
      margin-top: 8px;
      padding: 8px 14px 14px;
      border-top: 1px solid var(--divider-color, #eee);
    }

    .passive-entity-picker-wrap ha-entity-picker {
      width: 100%;
    }

    .passive-section-hint {
      font-size: 12px;
      color: var(--secondary-text-color);
      padding: 0 14px 10px;
      line-height: 1.4;
    }
  `;

  connectedCallback() {
    super.connectedCallback();
    this._initFromConfig();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._saveDebounce) clearTimeout(this._saveDebounce);
  }

  updated(changedProps: Map<string, unknown>) {
    const currentAreaId = this.config?.area_id ?? this.area?.area_id ?? null;
    const areaChanged = currentAreaId !== this._prevAreaId;

    if (areaChanged) {
      this._initFromConfig();
      this._prevAreaId = currentAreaId;
    } else if (changedProps.has("config") && !this._dirty) {
      const prevConfig = changedProps.get("config") as RoomConfig | null | undefined;
      if (prevConfig === null || prevConfig === undefined) {
        this._initFromConfig();
      }
    }
  }

  private _initFromConfig() {
    if (this.config) {
      this._selectedThermostats = new Set(this.config.thermostats);
      this._selectedAcs = new Set(this.config.acs);
      this._entityModes = { ...(this.config.entity_modes ?? {}) };
      this._selectedTempSensor = this.config.temperature_sensor;
      this._selectedHumiditySensor = this.config.humidity_sensor ?? "";
      this._selectedWindowSensors = new Set(this.config.window_sensors ?? []);
      this._windowOpenDelay = this.config.window_open_delay ?? 0;
      this._windowCloseDelay = this.config.window_close_delay ?? 0;
      this._climateMode = this.config.climate_mode;
      this._schedules = this.config.schedules ?? [];
      this._scheduleSelectorEntity = this.config.schedule_selector_entity ?? "";
      this._comfortHeat = this.config.comfort_heat ?? this.config.comfort_temp ?? 21.0;
      this._comfortCool = this.config.comfort_cool ?? 24.0;
      this._ecoHeat = this.config.eco_heat ?? this.config.eco_temp ?? 17.0;
      this._ecoCool = this.config.eco_cool ?? 27.0;
      this._selectedPresencePersons = this.config.presence_persons ?? [];
      this._displayName = this.config.display_name ?? "";
      this._heatingSystemType = this.config.heating_system_type ?? "";
      this._passiveDevices = (this.config.passive_devices ?? []).map(pd => ({ ...pd }));
      this._selectedCovers = new Set(this.config.covers ?? []);
      this._coversAutoEnabled = this.config.covers_auto_enabled ?? false;
      this._coversDeployThreshold = this.config.covers_deploy_threshold ?? 1.5;
      this._coversMinPosition = this.config.covers_min_position ?? 0;
      this._coversOverrideMinutes = this.config.covers_override_minutes ?? 60;
      this._coverSchedules = this.config.cover_schedules ?? [];
      this._coverScheduleSelectorEntity = this.config.cover_schedule_selector_entity ?? "";
      this._coversNightClose = this.config.covers_night_close ?? false;
      this._coversNightPosition = this.config.covers_night_position ?? 0;
      this._coversSensorOnly = this.config.covers_sensor_only ?? false;
      this._isOutdoor = this.config.is_outdoor ?? false;
      this._valveProtectionExclude = new Set(this.config.valve_protection_exclude ?? []);
      this._heatSourceOrchestration = this.config.heat_source_orchestration ?? false;
      this._heatSourcePrimaryDelta = this.config.heat_source_primary_delta ?? 1.5;
      this._heatSourceOutdoorThreshold = this.config.heat_source_outdoor_threshold ?? 5.0;
      this._heatSourceAcMinOutdoor = this.config.heat_source_ac_min_outdoor ?? -15.0;
    } else {
      this._selectedThermostats = new Set();
      this._selectedAcs = new Set();
      this._entityModes = {};
      this._selectedTempSensor = "";
      this._selectedHumiditySensor = "";
      this._selectedWindowSensors = new Set();
      this._windowOpenDelay = 0;
      this._windowCloseDelay = 0;
      this._climateMode = "auto";
      this._schedules = [];
      this._scheduleSelectorEntity = "";
      this._comfortHeat = 21.0;
      this._comfortCool = 24.0;
      this._ecoHeat = 17.0;
      this._ecoCool = 27.0;
      this._selectedPresencePersons = [];
      this._displayName = "";
      this._heatingSystemType = "";
      this._passiveDevices = [];
      this._selectedCovers = new Set();
      this._coversAutoEnabled = false;
      this._coversDeployThreshold = 1.5;
      this._coversMinPosition = 0;
      this._coversOverrideMinutes = 60;
      this._coverSchedules = [];
      this._coverScheduleSelectorEntity = "";
      this._coversNightClose = false;
      this._coversNightPosition = 0;
      this._coversSensorOnly = false;
      this._isOutdoor = false;
      this._valveProtectionExclude = new Set();
      this._heatSourceOrchestration = false;
      this._heatSourcePrimaryDelta = 1.5;
      this._heatSourceOutdoorThreshold = 5.0;
      this._heatSourceAcMinOutdoor = -15.0;
    }
    this._dirty = false;

    // Auto-detect editing mode
    const hasDevices =
      this._selectedThermostats.size > 0 ||
      this._selectedAcs.size > 0 ||
      !!this._selectedTempSensor;
    this._editingSchedule = this._schedules.length === 0;
    this._editingDevices = !hasDevices;
    this._editingCovers = this._selectedCovers.size === 0;
  }

  /** Expose effective override for hero-status via the override sub-component. */
  private _getEffectiveOverride(): {
    active: boolean;
    type: import("../types").OverrideType | null;
    temp: number | null;
    until: number | null;
  } {
    const overrideEl = this.shadowRoot?.querySelector(
      "rs-override-section",
    ) as RsOverrideSection | null;
    if (overrideEl) {
      return overrideEl.getEffectiveOverride();
    }
    // Fallback before sub-component mounts
    const live = this.config?.live;
    if (live?.override_active && live.override_type) {
      return {
        active: true,
        type: live.override_type,
        temp: live.override_temp,
        until: live.override_until,
      };
    }
    return { active: false, type: null, temp: null, until: null };
  }

  render() {
    if (!this.area) return nothing;

    return html`
      <div class="detail-layout">
        <div class="col-left">
          <rs-hero-status
            .hass=${this.hass}
            .area=${this.area}
            .config=${this.config}
            .isOutdoor=${this._isOutdoor}
            .overrideInfo=${this._getEffectiveOverride()}
            .climateControlActive=${this.climateControlActive}
            @display-name-changed=${this._onDisplayNameChanged}
          ></rs-hero-status>

          ${!this._isOutdoor
            ? html`
                <rs-section-card
                  icon="mdi:cog"
                  .heading=${localize("room.section.climate_mode", this.hass.language)}
                  hasInfo
                >
                  <div slot="info">
                    <b>${localize("mode.auto", this.hass.language)}</b> —
                    ${localize("mode.auto_desc", this.hass.language)}<br />
                    <b>${localize("mode.heat_only", this.hass.language)}</b> —
                    ${localize("mode.heat_only_desc", this.hass.language)}<br />
                    <b>${localize("mode.cool_only", this.hass.language)}</b> —
                    ${localize("mode.cool_only_desc", this.hass.language)}
                  </div>
                  <rs-climate-mode-selector
                    .climateMode=${this._climateMode}
                    .language=${this.hass.language}
                    @mode-changed=${this._onModeChanged}
                  ></rs-climate-mode-selector>
                </rs-section-card>

                <rs-section-card
                  icon="mdi:calendar"
                  .heading=${localize("room.section.schedule", this.hass.language)}
                  editable
                  .editing=${this._editingSchedule}
                  .doneLabel=${localize("schedule.done", this.hass.language)}
                  @edit-click=${() => {
                    this._editingSchedule = true;
                  }}
                  @done-click=${() => {
                    this._editingSchedule = false;
                  }}
                >
                  <rs-schedule-settings
                    .hass=${this.hass}
                    .schedules=${this._schedules}
                    .scheduleSelectorEntity=${this._scheduleSelectorEntity}
                    .activeScheduleIndex=${this.config?.live?.active_schedule_index ?? -1}
                    .comfortHeat=${this._comfortHeat}
                    .comfortCool=${this._comfortCool}
                    .ecoHeat=${this._ecoHeat}
                    .ecoCool=${this._ecoCool}
                    .climateMode=${this._climateMode}
                    .editing=${this._editingSchedule}
                    @schedules-changed=${this._onSchedulesChanged}
                    @schedule-selector-changed=${this._onScheduleSelectorChanged}
                    @comfort-heat-changed=${this._onComfortHeatChanged}
                    @comfort-cool-changed=${this._onComfortCoolChanged}
                    @eco-heat-changed=${this._onEcoHeatChanged}
                    @eco-cool-changed=${this._onEcoCoolChanged}
                  ></rs-schedule-settings>
                  ${this.config
                    ? html`
                        <rs-override-section
                          .hass=${this.hass}
                          .config=${this.config}
                          .climateMode=${this._climateMode}
                          .comfortHeat=${this._comfortHeat}
                          .comfortCool=${this._comfortCool}
                          .ecoHeat=${this._ecoHeat}
                          .ecoCool=${this._ecoCool}
                          .language=${this.hass.language}
                        ></rs-override-section>
                      `
                    : nothing}
                </rs-section-card>
              `
            : nothing}
          ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
        </div>

        <div class="col-right">
          ${!this._isOutdoor
            ? html`
                <rs-section-card
                  icon="mdi:power-plug"
                  .heading=${localize("room.section.devices", this.hass.language)}
                  editable
                  .editing=${this._editingDevices}
                  .doneLabel=${localize("devices.done", this.hass.language)}
                  @edit-click=${() => {
                    this._editingDevices = true;
                  }}
                  @done-click=${() => {
                    this._editingDevices = false;
                  }}
                >
                  <rs-device-section
                    .hass=${this.hass}
                    .area=${this.area}
                    .editing=${this._editingDevices}
                    .selectedThermostats=${this._selectedThermostats}
                    .selectedAcs=${this._selectedAcs}
                    .entityModes=${this._entityModes}
                    .selectedTempSensor=${this._selectedTempSensor}
                    .selectedHumiditySensor=${this._selectedHumiditySensor}
                    .selectedWindowSensors=${this._selectedWindowSensors}
                    .windowOpenDelay=${this._windowOpenDelay}
                    .windowCloseDelay=${this._windowCloseDelay}
                    .heatingSystemType=${this._heatingSystemType}
                    .valveProtectionExclude=${this._valveProtectionExclude}
                    .valveProtectionEnabled=${this.valveProtectionEnabled}
                    @climate-toggle=${this._onClimateToggle}
                    @device-type-change=${this._onDeviceTypeChange}
                    @entity-mode-change=${this._onEntityModeChange}
                    @sensor-selected=${this._onSensorSelected}
                    @window-sensor-toggle=${this._onWindowSensorToggle}
                    @window-open-delay-changed=${this._onWindowOpenDelayChanged}
                    @window-close-delay-changed=${this._onWindowCloseDelayChanged}
                    @external-entity-added=${this._onExternalEntityAdded}
                    @heating-system-type-changed=${this._onHeatingSystemTypeChanged}
                    @valve-protection-exclude-toggle=${this._onValveProtectionExcludeToggle}
                  ></rs-device-section>
                </rs-section-card>

                <rs-presence-section
                  .hass=${this.hass}
                  .presenceEnabled=${this.presenceEnabled}
                  .presencePersons=${this.presencePersons}
                  .selectedPresencePersons=${this._selectedPresencePersons}
                  .editing=${this._editingPresence}
                  .language=${this.hass.language}
                  @presence-persons-changed=${this._onPresencePersonsChanged}
                  @editing-changed=${this._onPresenceEditingChanged}
                ></rs-presence-section>
              `
            : nothing}
          ${!this._isOutdoor
            ? html`<rs-section-card
                icon="mdi:blinds-horizontal"
                .heading=${localize("room.section.covers", this.hass.language)}
                .badge=${localize("badge.beta", this.hass.language)}
                .badgeHint=${localize("badge.beta_hint", this.hass.language)}
                hasInfo
                editable
                .editing=${this._editingCovers}
                .doneLabel=${localize("covers.done", this.hass.language)}
                @edit-click=${() => {
                  this._editingCovers = true;
                }}
                @done-click=${() => {
                  this._editingCovers = false;
                }}
              >
                <div slot="info">
                  <b>${localize("covers.info.selection_title", this.hass.language)}</b><br />
                  ${localize("covers.info.selection_body", this.hass.language)}
                  <br /><br />
                  <b>${localize("covers.info.schedule_title", this.hass.language)}</b><br />
                  ${localize("covers.info.schedule_body", this.hass.language)}
                  <div class="yaml-block">
                    <span class="yaml-key">schedule</span>:
                    <span class="yaml-key">cover_evening</span>: <span class="yaml-key">name</span>:
                    <span class="yaml-value">Cover Evening</span>
                    <span class="yaml-key">monday</span>: - <span class="yaml-key">from</span>:
                    <span class="yaml-value">"20:00:00"</span> <span class="yaml-key">to</span>:
                    <span class="yaml-value">"06:00:00"</span> <span class="yaml-key">data</span>:
                    <span class="yaml-key">position</span>: <span class="yaml-value">10</span>
                  </div>
                  <b>${localize("covers.info.solar_title", this.hass.language)}</b><br />
                  ${localize("covers.info.solar_body", this.hass.language)}
                  <br /><br />
                  <b>${localize("covers.info.night_title", this.hass.language)}</b><br />
                  ${localize("covers.info.night_body", this.hass.language)}
                  <br /><br />
                  <b>${localize("covers.info.override_title", this.hass.language)}</b><br />
                  ${localize("covers.info.override_body", this.hass.language)}
                  <br /><br />
                  <b>${localize("covers.info.priority_title", this.hass.language)}</b><br />
                  ${localize("covers.info.priority_body", this.hass.language)}
                  <br /><br />
                  <b>${localize("covers.info.entities_title", this.hass.language)}</b><br />
                  ${localize("covers.info.entities_body", this.hass.language)}
                </div>
                <rs-covers-section
                  .hass=${this.hass}
                  .area=${this.area}
                  .editing=${this._editingCovers}
                  .selectedCovers=${this._selectedCovers}
                  .autoEnabled=${this._coversAutoEnabled}
                  .deployThreshold=${this._coversDeployThreshold}
                  .minPosition=${this._coversMinPosition}
                  .overrideMinutes=${this._coversOverrideMinutes}
                  .coverSchedules=${this._coverSchedules}
                  .coverScheduleSelectorEntity=${this._coverScheduleSelectorEntity}
                  .activeCoverScheduleIndex=${this.config?.live?.active_cover_schedule_index ?? -1}
                  .nightClose=${this._coversNightClose}
                  .nightPosition=${this._coversNightPosition}
                  .sensorOnly=${this._coversSensorOnly}
                  .forcedReason=${this.config?.live?.cover_forced_reason ?? ""}
                  .autoPaused=${this.config?.live?.cover_auto_paused ?? false}
                  @covers-toggle=${this._onCoversToggle}
                  @setting-changed=${this._onCoverSettingChanged}
                ></rs-covers-section>
              </rs-section-card>`
            : nothing}
          ${!this._isOutdoor &&
          this._selectedTempSensor &&
          this._selectedThermostats.size > 0 &&
          this._selectedAcs.size > 0
            ? html`<rs-section-card
                icon="mdi:swap-horizontal"
                .heading=${localize("room.section.heat_source", this.hass.language)}
              >
                <rs-heat-source-section
                  .hass=${this.hass}
                  .enabled=${this._heatSourceOrchestration}
                  .primaryDelta=${this._heatSourcePrimaryDelta}
                  .outdoorThreshold=${this._heatSourceOutdoorThreshold}
                  .acMinOutdoor=${this._heatSourceAcMinOutdoor}
                  @setting-changed=${this._onHeatSourceSettingChanged}
                ></rs-heat-source-section>
              </rs-section-card>`
            : nothing}

          ${this._renderPassiveDevicesSection()}

          <ha-card class="outdoor-toggle-card">
            <rs-toggle-row
              .label=${localize("room.outdoor_toggle", this.hass.language)}
              .hint=${localize("room.outdoor_hint", this.hass.language)}
              .checked=${this._isOutdoor}
              @toggle-changed=${this._onOutdoorToggle}
            ></rs-toggle-row>
          </ha-card>
        </div>
      </div>
    `;
  }

  // ---- Child event handlers ----

  private _onModeChanged(e: CustomEvent<{ mode: ClimateMode }>) {
    this._climateMode = e.detail.mode;
    this._autoSave();
  }

  private _onSchedulesChanged(e: CustomEvent<{ value: ScheduleEntry[] }>) {
    this._schedules = e.detail.value;
    this._autoSave();
  }

  private _onScheduleSelectorChanged(e: CustomEvent<{ value: string }>) {
    this._scheduleSelectorEntity = e.detail.value;
    this._autoSave();
  }

  private _onComfortHeatChanged(e: CustomEvent<{ value: number }>) {
    this._comfortHeat = e.detail.value;
    if (this._comfortCool < this._comfortHeat) this._comfortCool = this._comfortHeat;
    this._autoSave();
  }

  private _onComfortCoolChanged(e: CustomEvent<{ value: number }>) {
    this._comfortCool = e.detail.value;
    if (this._comfortHeat > this._comfortCool) this._comfortHeat = this._comfortCool;
    this._autoSave();
  }

  private _onEcoHeatChanged(e: CustomEvent<{ value: number }>) {
    this._ecoHeat = e.detail.value;
    if (this._ecoCool < this._ecoHeat) this._ecoCool = this._ecoHeat;
    this._autoSave();
  }

  private _onEcoCoolChanged(e: CustomEvent<{ value: number }>) {
    this._ecoCool = e.detail.value;
    if (this._ecoHeat > this._ecoCool) this._ecoHeat = this._ecoCool;
    this._autoSave();
  }

  private _onClimateToggle(
    e: CustomEvent<{ entityId: string; checked: boolean; detectedType: "thermostat" | "ac" }>,
  ) {
    const { entityId, checked, detectedType } = e.detail;
    if (checked) {
      const newThermostats = new Set(this._selectedThermostats);
      const newAcs = new Set(this._selectedAcs);
      if (detectedType === "ac") {
        newAcs.add(entityId);
      } else {
        newThermostats.add(entityId);
      }
      this._selectedThermostats = newThermostats;
      this._selectedAcs = newAcs;
    } else {
      const newThermostats = new Set(this._selectedThermostats);
      const newAcs = new Set(this._selectedAcs);
      newThermostats.delete(entityId);
      newAcs.delete(entityId);
      this._selectedThermostats = newThermostats;
      // Also remove from valve protection exclude list
      if (this._valveProtectionExclude.has(entityId)) {
        const nextExclude = new Set(this._valveProtectionExclude);
        nextExclude.delete(entityId);
        this._valveProtectionExclude = nextExclude;
      }
      this._selectedAcs = newAcs;
      const updatedModes = { ...this._entityModes };
      delete updatedModes[entityId];
      this._entityModes = updatedModes;
    }
    this._autoSave();
  }

  private _onEntityModeChange(
    e: CustomEvent<{ entityId: string; mode: "auto" | "heat_only" | "cool_only" }>,
  ) {
    const { entityId, mode } = e.detail;
    const updated = { ...this._entityModes };
    if (mode === "auto") {
      delete updated[entityId];
    } else {
      updated[entityId] = mode;
    }
    this._entityModes = updated;
    this._autoSave();
  }

  private _onDeviceTypeChange(e: CustomEvent<{ entityId: string; type: "thermostat" | "ac" }>) {
    const { entityId, type } = e.detail;
    const newThermostats = new Set(this._selectedThermostats);
    const newAcs = new Set(this._selectedAcs);

    if (type === "thermostat") {
      newAcs.delete(entityId);
      newThermostats.add(entityId);
    } else {
      newThermostats.delete(entityId);
      newAcs.add(entityId);
      // Moving to AC: remove from valve protection exclude list
      if (this._valveProtectionExclude.has(entityId)) {
        const nextExclude = new Set(this._valveProtectionExclude);
        nextExclude.delete(entityId);
        this._valveProtectionExclude = nextExclude;
      }
    }

    this._selectedThermostats = newThermostats;
    this._selectedAcs = newAcs;
    this._autoSave();
  }

  private _onSensorSelected(e: CustomEvent<{ entityId: string; type: "temp" | "humidity" }>) {
    if (e.detail.type === "temp") {
      this._selectedTempSensor = e.detail.entityId;
    } else {
      this._selectedHumiditySensor = e.detail.entityId;
    }
    this._autoSave();
  }

  private _onWindowSensorToggle(e: CustomEvent<{ entityId: string; checked: boolean }>) {
    const { entityId, checked } = e.detail;
    const next = new Set(this._selectedWindowSensors);
    if (checked) {
      next.add(entityId);
    } else {
      next.delete(entityId);
    }
    this._selectedWindowSensors = next;
    this._autoSave();
  }

  private _onWindowOpenDelayChanged(e: CustomEvent<{ value: number }>) {
    this._windowOpenDelay = e.detail.value;
    this._autoSave();
  }

  private _onWindowCloseDelayChanged(e: CustomEvent<{ value: number }>) {
    this._windowCloseDelay = e.detail.value;
    this._autoSave();
  }

  private _onHeatingSystemTypeChanged(e: CustomEvent<{ value: string }>) {
    this._heatingSystemType = e.detail.value;
    this._autoSave();
  }

  private _onValveProtectionExcludeToggle(e: CustomEvent<{ entityId: string; excluded: boolean }>) {
    const { entityId, excluded } = e.detail;
    const next = new Set(this._valveProtectionExclude);
    if (excluded) {
      next.add(entityId);
    } else {
      next.delete(entityId);
    }
    this._valveProtectionExclude = next;
    this._autoSave();
  }

  private _onExternalEntityAdded(
    e: CustomEvent<{
      entityId: string;
      category: "climate" | "temp" | "humidity" | "window";
      detectedType?: "thermostat" | "ac";
    }>,
  ) {
    const { entityId, category, detectedType } = e.detail;
    if (category === "climate") {
      const newThermostats = new Set(this._selectedThermostats);
      const newAcs = new Set(this._selectedAcs);
      if (detectedType === "ac") {
        newAcs.add(entityId);
      } else {
        newThermostats.add(entityId);
      }
      this._selectedThermostats = newThermostats;
      this._selectedAcs = newAcs;
    } else if (category === "temp") {
      this._selectedTempSensor = entityId;
    } else if (category === "window") {
      const next = new Set(this._selectedWindowSensors);
      next.add(entityId);
      this._selectedWindowSensors = next;
    } else {
      this._selectedHumiditySensor = entityId;
    }
    this._autoSave();
  }

  private _onPresencePersonsChanged(e: CustomEvent<string[]>) {
    this._selectedPresencePersons = e.detail;
    this._autoSave();
  }

  private _onPresenceEditingChanged(e: CustomEvent<{ editing: boolean }>) {
    this._editingPresence = e.detail.editing;
  }

  // ---- Cover event handlers ----

  private _onCoversToggle(e: CustomEvent<{ entityId: string; checked: boolean }>) {
    const { entityId, checked } = e.detail;
    const next = new Set(this._selectedCovers);
    if (checked) {
      next.add(entityId);
    } else {
      next.delete(entityId);
    }
    this._selectedCovers = next;
    this._autoSave();
  }

  private _onCoverSettingChanged(e: CustomEvent<{ key: string; value: unknown }>) {
    const { key, value } = e.detail;
    e.stopPropagation();
    if (key === "covers_auto_enabled") this._coversAutoEnabled = value as boolean;
    else if (key === "covers_deploy_threshold") this._coversDeployThreshold = value as number;
    else if (key === "covers_min_position") this._coversMinPosition = value as number;
    else if (key === "covers_override_minutes") this._coversOverrideMinutes = value as number;
    else if (key === "cover_schedules") this._coverSchedules = value as CoverScheduleEntry[];
    else if (key === "cover_schedule_selector_entity")
      this._coverScheduleSelectorEntity = value as string;
    else if (key === "covers_night_close") this._coversNightClose = value as boolean;
    else if (key === "covers_night_position") this._coversNightPosition = value as number;
    else if (key === "covers_sensor_only") this._coversSensorOnly = value as boolean;
    this._autoSave();
  }

  // ---- Heat source orchestration ----

  private _onHeatSourceSettingChanged(e: CustomEvent<{ key: string; value: unknown }>) {
    const { key, value } = e.detail;
    e.stopPropagation();
    if (key === "heat_source_orchestration") this._heatSourceOrchestration = value as boolean;
    else if (key === "heat_source_primary_delta") this._heatSourcePrimaryDelta = value as number;
    else if (key === "heat_source_outdoor_threshold")
      this._heatSourceOutdoorThreshold = value as number;
    else if (key === "heat_source_ac_min_outdoor") this._heatSourceAcMinOutdoor = value as number;
    this._autoSave();
  }

  // ---- Outdoor toggle ----

  private _onOutdoorToggle(e: CustomEvent<boolean>) {
    this._isOutdoor = e.detail;
    this._autoSave();
  }

  // ---- Auto-save ----

  private _onDisplayNameChanged(e: CustomEvent<{ value: string }>) {
    this._displayName = e.detail.value;
    this._autoSave();
  }

  private _autoSave() {
    this._dirty = true;
    if (this._saveDebounce) clearTimeout(this._saveDebounce);
    this._saveDebounce = setTimeout(() => this._doSave(), 500);
  }

  private async _doSave() {
    fireSaveStatus(this, "saving");
    this._error = "";

    try {
      await this.hass.callWS({
        type: "roommind/rooms/save",
        area_id: this.area.area_id,
        thermostats: [...this._selectedThermostats],
        acs: [...this._selectedAcs],
        temperature_sensor: this._selectedTempSensor,
        humidity_sensor: this._selectedHumiditySensor,
        window_sensors: [...this._selectedWindowSensors],
        window_open_delay: this._windowOpenDelay,
        window_close_delay: this._windowCloseDelay,
        climate_mode: this._climateMode,
        schedules: this._schedules,
        schedule_selector_entity: this._scheduleSelectorEntity,
        comfort_heat: this._comfortHeat,
        comfort_cool: this._comfortCool,
        eco_heat: this._ecoHeat,
        eco_cool: this._ecoCool,
        presence_persons: this._selectedPresencePersons.filter((p) => p),
        display_name: this._displayName,
        heating_system_type: this._heatingSystemType,
        entity_modes: this._entityModes,
        passive_devices: this._passiveDevices,
        covers: [...this._selectedCovers],
        covers_auto_enabled: this._coversAutoEnabled,
        covers_deploy_threshold: this._coversDeployThreshold,
        covers_min_position: this._coversMinPosition,
        covers_override_minutes: this._coversOverrideMinutes,
        cover_schedules: this._coverSchedules,
        cover_schedule_selector_entity: this._coverScheduleSelectorEntity,
        covers_night_close: this._coversNightClose,
        covers_night_position: this._coversNightPosition,
        covers_sensor_only: this._coversSensorOnly,
        is_outdoor: this._isOutdoor,
        valve_protection_exclude: [...this._valveProtectionExclude],
        heat_source_orchestration: this._heatSourceOrchestration,
        heat_source_primary_delta: this._heatSourcePrimaryDelta,
        heat_source_outdoor_threshold: this._heatSourceOutdoorThreshold,
        heat_source_ac_min_outdoor: this._heatSourceAcMinOutdoor,
      });

      this._dirty = false;
      fireSaveStatus(this, "saved");

      this.dispatchEvent(
        new CustomEvent("room-updated", {
          bubbles: true,
          composed: true,
        }),
      );
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : localize("room.error_save_fallback", this.hass.language);
      this._error = message;
      fireSaveStatus(this, "error");
    }
  }

  private _renderPassiveDevicesSection() {
    const lang = this.hass.language;
    const editing = this._editingPassiveDevices;

    return html`
      <rs-section-card
        icon="mdi:eye-outline"
        .heading=${localize("passive_devices.section_title", lang)}
        editable
        .editing=${editing}
        .doneLabel=${localize("schedule.done", lang)}
        @edit-click=${() => {
          this._editingPassiveDevices = true;
        }}
        @done-click=${() => {
          this._editingPassiveDevices = false;
        }}
      >
        ${editing
          ? html`<p class="passive-section-hint">
              ${localize("passive_devices.section_hint", lang)}
            </p>`
          : nothing}
        ${this._passiveDevices.length === 0 && !editing
          ? html`<div style="padding: 0 14px 14px">
              <span class="field-hint"
                >${localize("passive_devices.none_configured", lang)}</span
              >
            </div>`
          : this._passiveDevices.map((pd, i) => this._renderPassiveDeviceRow(pd, i, editing))}
        ${editing
          ? html`
              <div class="passive-entity-picker-wrap">
                <ha-entity-picker
                  .hass=${this.hass}
                  .includeDomains=${["climate", "binary_sensor", "input_boolean"]}
                  .entityFilter=${this._passiveEntityFilter}
                  .value=${""}
                  label=${localize("passive_devices.add", lang)}
                  @value-changed=${this._onPassiveEntityPicked}
                ></ha-entity-picker>
              </div>
            `
          : nothing}
      </rs-section-card>
    `;
  }

  private _renderPassiveDeviceRow(pd: PassiveDevice, i: number, editing: boolean) {
    const lang = this.hass.language;
    const entityState = this.hass.states[pd.entity_id];
    const friendlyName = (entityState?.attributes?.friendly_name as string) || pd.entity_id;
    const modeBadgeLabel =
      pd.mode === "auto"
        ? localize("passive_devices.mode_auto", lang)
        : pd.mode === "cooling"
          ? localize("passive_devices.mode_cooling", lang)
          : localize("passive_devices.mode_heating", lang);

    return html`
      <div class="passive-device-row">
        <div class="passive-device-info">
          <div class="passive-device-name">${friendlyName}</div>
          <div class="passive-device-entity">${pd.entity_id}</div>
        </div>
        ${editing
          ? html`
              <div class="passive-selects">
                <ha-select
                  class="passive-select"
                  outlined
                  .value=${pd.mode}
                  @selected=${(e: Event) => {
                    const val =
                      (e as CustomEvent).detail?.value ??
                      (e.target as HTMLSelectElement).value;
                    if (!val) return;
                    const updated = [...this._passiveDevices];
                    updated[i] = {
                      ...updated[i],
                      mode: val as "auto" | "cooling" | "heating",
                    };
                    this._passiveDevices = updated;
                    this._autoSave();
                  }}
                  @closed=${(e: Event) => e.stopPropagation()}
                  fixedMenuPosition
                >
                  <ha-list-item value="auto"
                    >${localize("passive_devices.mode_auto", lang)}</ha-list-item
                  >
                  <ha-list-item value="cooling"
                    >${localize("passive_devices.mode_cooling", lang)}</ha-list-item
                  >
                  <ha-list-item value="heating"
                    >${localize("passive_devices.mode_heating", lang)}</ha-list-item
                  >
                </ha-select>
                <ha-textfield
                  class="passive-pf-field"
                  type="number"
                  min="0.01"
                  max="5"
                  step="0.1"
                  .label=${localize("passive_devices.power_fraction", lang)}
                  .value=${String(pd.power_fraction)}
                  @change=${(e: Event) => {
                    const val = parseFloat((e.target as HTMLInputElement).value);
                    if (!val || val <= 0) return;
                    const updated = [...this._passiveDevices];
                    updated[i] = { ...updated[i], power_fraction: val };
                    this._passiveDevices = updated;
                    this._autoSave();
                  }}
                ></ha-textfield>
              </div>
              <button
                class="passive-remove-btn"
                title=${localize("passive_devices.remove", lang)}
                @click=${() => {
                  this._passiveDevices = this._passiveDevices.filter((_, idx) => idx !== i);
                  this._autoSave();
                }}
              >
                <ha-icon icon="mdi:close" style="--mdc-icon-size: 18px"></ha-icon>
              </button>
            `
          : html`
              <span class="passive-mode-badge">${modeBadgeLabel}</span>
              <span
                style="font-size:12px; color:var(--secondary-text-color); flex-shrink:0"
                >${pd.power_fraction}×</span
              >
            `}
      </div>
    `;
  }

  private _passiveEntityFilter = (entity: { entity_id: string }): boolean => {
    const id = entity.entity_id;
    return !this._passiveDevices.some((pd) => pd.entity_id === id);
  };

  private _onPassiveEntityPicked(e: CustomEvent) {
    const entityId = e.detail?.value as string;
    if (!entityId) return;
    if (this._passiveDevices.some((pd) => pd.entity_id === entityId)) return;
    // Default mode: "auto" for climate entities, "cooling" for others
    const defaultMode = entityId.startsWith("climate.") ? "auto" : "cooling";
    this._passiveDevices = [
      ...this._passiveDevices,
      { entity_id: entityId, mode: defaultMode, power_fraction: 1.0 },
    ];
    this._autoSave();
    // Clear picker
    const picker = e.target as HTMLElement & { value: string };
    picker.value = "";
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-room-detail": RsRoomDetail;
  }
}
