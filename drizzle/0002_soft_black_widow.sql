ALTER TABLE "source_document" ADD COLUMN "file_name" text;--> statement-breakpoint
ALTER TABLE "source_document" ADD COLUMN "source_uri" text;--> statement-breakpoint
ALTER TABLE "source_document" ADD COLUMN "corpus" text;--> statement-breakpoint
ALTER TABLE "source_document" ADD COLUMN "coverage_start_year" integer;--> statement-breakpoint
ALTER TABLE "source_document" ADD COLUMN "coverage_end_year" integer;--> statement-breakpoint
ALTER TABLE "source_document" ADD COLUMN "section_range" text;--> statement-breakpoint
ALTER TABLE "source_document" ADD COLUMN "page_count" integer;--> statement-breakpoint
ALTER TABLE "source_document" ADD COLUMN "media_format" text;