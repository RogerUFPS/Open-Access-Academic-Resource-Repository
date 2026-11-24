import { CATALOG_RESOURCES } from "./catalogAdminService.js";

const ACTIONS = ["view", "create", "update", "delete", "restore"];

export function catalogResourcePermissions(user, resource) {
  const permissions = user?.effective_permissions?.catalog?.[resource] ?? {};
  return Object.fromEntries(ACTIONS.map((action) => [
    action,
    Boolean(user?.is_superadmin || permissions[action] === true),
  ]));
}

export function viewableCatalogResources(user) {
  return Object.keys(CATALOG_RESOURCES).filter(
    (resource) => catalogResourcePermissions(user, resource).view
  );
}
