// Apply with mongosh against the mediflow database.
// Preserve the active validator and add the optional logical-archive timestamp.
const mediflow = db.getSiblingDB("mediflow");
const collections = mediflow.getCollectionInfos({ name: "medical_documents" });

if (collections.length === 0) {
  throw new Error("Collection medical_documents introuvable.");
}

const validator = collections[0].options.validator;
if (!validator || !validator.$jsonSchema) {
  throw new Error("Le validateur JSON Schema de medical_documents est introuvable.");
}

if (!validator.$jsonSchema.properties) {
  validator.$jsonSchema.properties = {};
}
validator.$jsonSchema.properties.archivedAt = { bsonType: ["date", "null"] };

const result = mediflow.runCommand({
  collMod: "medical_documents",
  validator,
  validationLevel: collections[0].options.validationLevel || "strict",
  validationAction: collections[0].options.validationAction || "error",
});

if (result.ok !== 1) {
  throw new Error(`Échec de la mise à jour du validateur: ${JSON.stringify(result)}`);
}

print("Validateur medical_documents mis à jour : archivedAt est autorisé.");
