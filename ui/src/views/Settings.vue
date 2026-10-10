<!--
  Copyright (C) 2022 Nethesis S.r.l.
  SPDX-License-Identifier: GPL-3.0-or-later
-->
<template>
  <cv-grid fullWidth>
    <cv-row>
      <cv-column class="page-title">
        <h2>{{ $t("settings.title") }}</h2>
      </cv-column>
    </cv-row>
    <cv-row v-if="error.getConfiguration">
      <cv-column>
        <NsInlineNotification
          kind="error"
          :title="$t('action.get-configuration')"
          :description="error.getConfiguration"
          :showCloseButton="false"
        />
      </cv-column>
    </cv-row>
    <!-- management UI login -->
    <cv-row v-if="url">
      <cv-column>
        <cv-tile light>
          <h4 class="mg-bottom">{{ $t("settings.management_title") }}</h4>
          <p class="mg-bottom helper">
            {{ $t("settings.management_description") }}
          </p>
          <cv-text-input
            id="maubot-url"
            :label="$t('settings.management_url')"
            :value="url"
            readonly
            class="mg-bottom"
          />
          <cv-text-input
            id="maubot-admin-user"
            :label="$t('settings.admin_user')"
            :value="adminUser"
            readonly
            class="mg-bottom"
          />
          <cv-text-input
            id="maubot-admin-password"
            :label="$t('settings.admin_password')"
            :value="adminPassword"
            type="password"
            readonly
            class="mg-bottom"
          />
          <NsButton
            kind="secondary"
            :icon="Launch20"
            @click="openManagementUi"
            >{{ $t("settings.open_management") }}</NsButton
          >
        </cv-tile>
      </cv-column>
    </cv-row>
    <cv-row>
      <cv-column>
        <cv-tile light>
          <cv-form @submit.prevent="configureModule">
            <cv-text-input
              :label="$t('settings.maubot_fqdn')"
              placeholder="maubot.example.org"
              v-model.trim="host"
              class="mg-bottom"
              :invalid-message="$t(error.host)"
              :disabled="loading.getConfiguration || loading.configureModule"
              ref="host"
            >
            </cv-text-input>
            <cv-toggle
              value="letsEncrypt"
              :label="$t('settings.lets_encrypt')"
              v-model="isLetsEncryptEnabled"
              :disabled="loading.getConfiguration || loading.configureModule"
              class="mg-bottom"
            >
              <template slot="text-left">{{
                $t("settings.disabled")
              }}</template>
              <template slot="text-right">{{
                $t("settings.enabled")
              }}</template>
            </cv-toggle>
            <cv-toggle
              value="httpToHttps"
              :label="$t('settings.http_to_https')"
              v-model="isHttpToHttpsEnabled"
              :disabled="loading.getConfiguration || loading.configureModule"
              class="mg-bottom"
            >
              <template slot="text-left">{{
                $t("settings.disabled")
              }}</template>
              <template slot="text-right">{{
                $t("settings.enabled")
              }}</template>
            </cv-toggle>
            <!-- homeservers -->
            <h4 class="mg-bottom-sm">{{ $t("settings.homeservers_title") }}</h4>
            <p class="mg-bottom helper">
              {{ $t("settings.homeservers_description") }}
            </p>
            <div
              v-for="(homeserver, index) in homeservers"
              :key="homeserver.key"
              class="homeserver mg-bottom"
            >
              <cv-text-input
                :id="'homeserver-name-' + index"
                :label="$t('settings.homeserver_name')"
                placeholder="example.org"
                v-model.trim="homeserver.name"
                :invalid-message="$t(homeserverError(index, 'name'))"
                :disabled="loading.getConfiguration || loading.configureModule"
                :ref="'homeservers.' + index + '.name'"
              />
              <cv-text-input
                :id="'homeserver-url-' + index"
                :label="$t('settings.homeserver_url')"
                placeholder="https://matrix.example.org"
                v-model.trim="homeserver.url"
                :invalid-message="$t(homeserverError(index, 'url'))"
                :disabled="loading.getConfiguration || loading.configureModule"
                :ref="'homeservers.' + index + '.url'"
              />
              <cv-text-input
                :id="'homeserver-secret-' + index"
                :label="$t('settings.homeserver_secret')"
                v-model="homeserver.secret"
                type="password"
                :disabled="loading.getConfiguration || loading.configureModule"
              />
              <NsButton
                kind="danger--ghost"
                size="small"
                :icon="TrashCan20"
                :disabled="loading.getConfiguration || loading.configureModule"
                @click="removeHomeserver(index)"
                >{{ $t("settings.remove_homeserver") }}</NsButton
              >
            </div>
            <NsButton
              kind="secondary"
              size="small"
              :icon="Add20"
              :disabled="loading.getConfiguration || loading.configureModule"
              class="mg-bottom"
              @click="addHomeserver"
              >{{ $t("settings.add_homeserver") }}</NsButton
            >
            <!-- admin password -->
            <cv-text-input
              id="new-admin-password"
              :label="$t('settings.new_admin_password')"
              :helper-text="$t('settings.new_admin_password_helper')"
              v-model="newAdminPassword"
              type="password"
              autocomplete="new-password"
              :invalid-message="$t(error.admin_password)"
              :disabled="loading.getConfiguration || loading.configureModule"
              class="mg-bottom"
              ref="admin_password"
            />
            <cv-row v-if="error.configureModule">
              <cv-column>
                <NsInlineNotification
                  kind="error"
                  :title="$t('action.configure-module')"
                  :description="error.configureModule"
                  :showCloseButton="false"
                />
              </cv-column>
            </cv-row>
            <NsButton
              kind="primary"
              :icon="Save20"
              :loading="loading.configureModule"
              :disabled="loading.getConfiguration || loading.configureModule"
              >{{ $t("settings.save") }}</NsButton
            >
          </cv-form>
        </cv-tile>
      </cv-column>
    </cv-row>
  </cv-grid>
</template>

<script>
import to from "await-to-js";
import { mapState } from "vuex";
import {
  QueryParamService,
  UtilService,
  TaskService,
  IconService,
  PageTitleService,
} from "@nethserver/ns8-ui-lib";

let homeserverKey = 0;

export default {
  name: "Settings",
  mixins: [
    TaskService,
    IconService,
    UtilService,
    QueryParamService,
    PageTitleService,
  ],
  pageTitle() {
    return this.$t("settings.title") + " - " + this.appName;
  },
  data() {
    return {
      q: {
        page: "settings",
      },
      urlCheckInterval: null,
      host: "",
      isLetsEncryptEnabled: false,
      isHttpToHttpsEnabled: true,
      url: "",
      adminUser: "",
      adminPassword: "",
      newAdminPassword: "",
      homeservers: [],
      // Validation errors of homeserver fields, keyed "<index>.<field>"
      homeserverErrors: {},
      loading: {
        getConfiguration: false,
        configureModule: false,
      },
      error: {
        getConfiguration: "",
        configureModule: "",
        host: "",
        lets_encrypt: "",
        http2https: "",
        admin_password: "",
      },
    };
  },
  computed: {
    ...mapState(["instanceName", "core", "appName"]),
  },
  created() {
    this.getConfiguration();
  },
  beforeRouteEnter(to, from, next) {
    next((vm) => {
      vm.watchQueryData(vm);
      vm.urlCheckInterval = vm.initUrlBindingForApp(vm, vm.q.page);
    });
  },
  beforeRouteLeave(to, from, next) {
    clearInterval(this.urlCheckInterval);
    next();
  },
  methods: {
    // Start a module task and route its events to the given handlers
    async runTask(action, data, handlers, extra) {
      const eventId = this.getUuid();
      this.core.$root.$once(`${action}-aborted-${eventId}`, handlers.aborted);
      this.core.$root.$once(
        `${action}-completed-${eventId}`,
        handlers.completed
      );
      if (handlers.validationFailed) {
        this.core.$root.$once(
          `${action}-validation-failed-${eventId}`,
          handlers.validationFailed
        );
      }
      const res = await to(
        this.createModuleTaskForApp(this.instanceName, {
          action,
          data,
          extra: {
            title: this.$t("action." + action),
            isNotificationHidden: true,
            ...extra,
            eventId,
          },
        })
      );
      return res[0];
    },
    newHomeserver(item) {
      homeserverKey += 1;
      return {
        key: homeserverKey,
        name: item ? item.name : "",
        url: item ? item.url : "",
        secret: item ? item.secret : "",
      };
    },
    addHomeserver() {
      this.homeservers.push(this.newHomeserver());
      const index = this.homeservers.length - 1;
      this.$nextTick(() => this.focusElement(`homeservers.${index}.name`));
    },
    removeHomeserver(index) {
      this.homeservers.splice(index, 1);
      this.homeserverErrors = {};
    },
    homeserverError(index, field) {
      return this.homeserverErrors[`${index}.${field}`] || "";
    },
    focusElement(ref) {
      // v-for refs are arrays
      const element = Array.isArray(this.$refs[ref])
        ? this.$refs[ref][0]
        : this.$refs[ref];
      if (element && element.focus) {
        element.focus();
      }
    },
    openManagementUi() {
      window.open(this.url, "_blank", "noopener");
    },
    async getConfiguration() {
      this.loading.getConfiguration = true;
      this.error.getConfiguration = "";
      const err = await this.runTask("get-configuration", undefined, {
        aborted: this.getConfigurationAborted,
        completed: this.getConfigurationCompleted,
      });
      if (err) {
        console.error("error creating task get-configuration", err);
        this.error.getConfiguration = this.getErrorMessage(err);
        this.loading.getConfiguration = false;
      }
    },
    getConfigurationAborted(taskResult, taskContext) {
      console.error(`${taskContext.action} aborted`, taskResult);
      this.error.getConfiguration = this.$t("error.generic_error");
      this.loading.getConfiguration = false;
    },
    getConfigurationCompleted(taskContext, taskResult) {
      const config = taskResult.output;
      this.host = config.host;
      this.isLetsEncryptEnabled = config.lets_encrypt;
      this.isHttpToHttpsEnabled = config.http2https;
      this.url = config.url;
      this.adminUser = config.admin_user;
      this.adminPassword = config.admin_password;
      this.homeservers = config.homeservers.map((item) =>
        this.newHomeserver(item)
      );
      this.newAdminPassword = "";
      this.loading.getConfiguration = false;
      this.$nextTick(() => this.focusElement("host"));
    },
    validateConfigureModule() {
      this.clearErrors(this);
      this.homeserverErrors = {};
      let firstInvalid = "";
      if (!this.host) {
        this.error.host = "common.required";
        firstInvalid = "host";
      }
      const names = new Set();
      const errors = {};
      this.homeservers.forEach((homeserver, index) => {
        const name = homeserver.name.toLowerCase();
        if (!name) {
          errors[`${index}.name`] = "common.required";
        } else if (names.has(name)) {
          errors[`${index}.name`] = "settings.duplicate_server_name";
        }
        names.add(name);
        if (!/^https?:\/\/[^\s/?#]+/.test(homeserver.url)) {
          errors[`${index}.url`] = "settings.invalid_homeserver_url";
        }
      });
      if (!firstInvalid && Object.keys(errors).length) {
        firstInvalid = "homeservers." + Object.keys(errors)[0];
      }
      this.homeserverErrors = errors;
      if (firstInvalid) {
        this.$nextTick(() => this.focusElement(firstInvalid));
        return false;
      }
      return true;
    },
    // Show task validation errors next to their fields
    showValidationErrors(validationErrors) {
      const homeserverErrors = {};
      let firstInvalid = "";
      for (const validationError of validationErrors) {
        const param = validationError.parameter;
        const match = /^homeservers\.(\d+\.(name|url))$/.exec(param);
        if (match) {
          homeserverErrors[match[1]] = "settings." + validationError.error;
        } else {
          this.error[param] = "settings." + validationError.error;
        }
        firstInvalid = firstInvalid || param;
      }
      this.homeserverErrors = homeserverErrors;
      if (firstInvalid) {
        this.$nextTick(() => this.focusElement(firstInvalid));
      }
    },
    async configureModule() {
      if (!this.validateConfigureModule()) {
        return;
      }
      this.loading.configureModule = true;
      const data = {
        host: this.host,
        lets_encrypt: this.isLetsEncryptEnabled,
        http2https: this.isHttpToHttpsEnabled,
        homeservers: this.homeservers.map((homeserver) => ({
          name: homeserver.name,
          url: homeserver.url,
          secret: homeserver.secret,
        })),
      };
      if (this.newAdminPassword) {
        data.admin_password = this.newAdminPassword;
      }
      const err = await this.runTask(
        "configure-module",
        data,
        {
          aborted: this.configureModuleAborted,
          completed: this.configureModuleCompleted,
          validationFailed: this.configureModuleValidationFailed,
        },
        {
          title: this.$t("settings.instance_configuration", {
            instance: this.instanceName,
          }),
          description: this.$t("settings.configuring"),
          isNotificationHidden: false,
        }
      );
      if (err) {
        console.error("error creating task configure-module", err);
        this.error.configureModule = this.getErrorMessage(err);
        this.loading.configureModule = false;
      }
    },
    configureModuleValidationFailed(validationErrors) {
      this.loading.configureModule = false;
      this.showValidationErrors(validationErrors);
    },
    configureModuleAborted(taskResult, taskContext) {
      console.error(`${taskContext.action} aborted`, taskResult);
      this.error.configureModule = this.$t("error.generic_error");
      this.loading.configureModule = false;
    },
    configureModuleCompleted() {
      this.loading.configureModule = false;
      this.getConfiguration();
    },
  },
};
</script>

<style scoped lang="scss">
@import "../styles/carbon-utils";

.mg-bottom {
  margin-bottom: $spacing-06;
}

.mg-bottom-sm {
  margin-bottom: $spacing-03;
}

.homeserver {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: $spacing-05;
  align-items: end;
  padding-bottom: $spacing-05;
  border-bottom: 1px solid $ui-03;
}

.helper {
  max-width: 38rem;
}
</style>
