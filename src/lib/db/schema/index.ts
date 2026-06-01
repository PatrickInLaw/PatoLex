/**
 * PatoLex DB schema barrel — re-exports all tables, enums, and custom types.
 * Import from here to get the full schema in one place.
 */

// Custom column types
export { daterange, tsvector } from "./_types.js";

// Enums
export {
  unitTypeEnum,
  provisionStatusEnum,
  changeActionEnum,
  enactmentKindEnum,
  sourceTypeEnum,
  trustLevelEnum,
  lineageEdgeTypeEnum,
} from "./enums.js";

// Tables
export { sourceDocument } from "./source-document.js";
export { enactment } from "./enactment.js";
export { provision } from "./provision.js";
export { designationHistory } from "./designation-history.js";
export { changeEvent } from "./change-event.js";
export { lineageEdge } from "./lineage-edge.js";
export { provisionVersion } from "./provision-version.js";
