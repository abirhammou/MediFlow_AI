// =====================================================================
// MediFlow AI — application user (runs before mongo-init.js)
// Executed by the mongo:7 entrypoint as the root user, on first start only.
// Creates `mediflow_app` with readWrite on `mediflow` (and nothing else).
// The password comes from the MONGO_APP_PASSWORD environment variable.
// Re-runnable by hand:
//   MONGO_APP_PASSWORD=... mongosh "mongodb://root:...@localhost:27017/admin" 00-create-user.js
// =====================================================================

const APP_DB = "mediflow";
const APP_USER = "mediflow_app";
const appPassword = process.env.MONGO_APP_PASSWORD;

if (!appPassword) {
  throw new Error("MONGO_APP_PASSWORD is not set: cannot create the application user.");
}

const appDb = db.getSiblingDB(APP_DB);
const roles = [{ role: "readWrite", db: APP_DB }];

if (appDb.getUser(APP_USER)) {
  appDb.updateUser(APP_USER, { pwd: appPassword, roles });
  print(`✔ user ${APP_USER} updated`);
} else {
  appDb.createUser({ user: APP_USER, pwd: appPassword, roles });
  print(`✔ user ${APP_USER} created`);
}
