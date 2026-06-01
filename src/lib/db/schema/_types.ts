/**
 * Custom Drizzle column types for PostgreSQL features not natively supported.
 */

import { customType } from "drizzle-orm/pg-core";

/**
 * daterange — PostgreSQL range type for [valid_from, valid_to) intervals.
 *
 * Drizzle has no native daterange support. We map it to a custom type so
 * schema definitions can reference it; the actual SQL type is `daterange`.
 *
 * JavaScript representation: a string in PostgreSQL range literal syntax,
 * e.g. "[2023-01-01,2024-01-01)" or "[2023-01-01,)".
 * The application layer is responsible for encoding/decoding range literals.
 */
export const daterange = customType<{
  data: string;
  driverData: string;
}>({
  dataType() {
    return "daterange";
  },
});

/**
 * tsvector — PostgreSQL full-text search vector type (retained for reference).
 *
 * provision_version.fts_vector uses this custom type together with Drizzle's
 * generatedAlwaysAs() to emit `tsvector GENERATED ALWAYS AS (...) STORED` DDL
 * natively. See provision-version.ts.
 *
 * See drizzle/README.md for the full list of hand-edited migration sections.
 */
export const tsvector = customType<{
  data: string;
  driverData: string;
}>({
  dataType() {
    return "tsvector";
  },
});
