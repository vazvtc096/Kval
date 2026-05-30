import eslint from "@eslint/js";
import tseslint from "typescript-eslint";
import eslintConfigPrettier from "eslint-config-prettier";

export default tseslint.config(
  {
    ignores: ["out/**", "node_modules/**"],
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  eslintConfigPrettier,
  {
    files: ["src/**/*.ts"],
    languageOptions: {
      parserOptions: {
        project: false,
      },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
    },
  }
);
