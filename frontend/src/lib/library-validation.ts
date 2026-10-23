type Translate = (
  text: string,
  parameters?: Record<string, string | number>,
) => string;

const fieldLabels: Record<string, string> = {
  slug: "Identifier",
  name: "Name",
  objective: "Objective",
  instructions: "Instructions",
  enabled: "Active",
  compatibility: "Compatible assistants",
  required_capabilities: "Required capabilities",
  skills: "Required skills",
  expected_checks: "Expected checks",
  expected_version: "Version",
};

export function libraryValidationMessage(
  message: string,
  t: Translate,
): string {
  const prefix = "Invalid field: ";
  if (!message.startsWith(prefix)) return t(message);
  const [name, index] = message.slice(prefix.length).split(".");
  let field = t(fieldLabels[name] || "Definition");
  if (index && /^\d+$/.test(index))
    field = t("{field}, item {number}", { field, number: Number(index) + 1 });
  return t("Check the {field} field.", { field });
}
