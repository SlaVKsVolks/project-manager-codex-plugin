const configuredRemoteUrl = import.meta.env?.VITE_PROJECT_MANAGER_REMOTE_DATA_URL;

export const REMOTE_DATA_URL = configuredRemoteUrl ||
  'https://raw.githubusercontent.com/SlaVKsVolks/project-manager-codex-plugin/main/site/src/data/project-manager.json';
