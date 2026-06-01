ALTER TABLE "source_document" ADD COLUMN "content_sha256" text;--> statement-breakpoint
ALTER TABLE "source_document" ADD COLUMN "edition_year" integer;--> statement-breakpoint
ALTER TABLE "source_document" ADD COLUMN "claimed_year" integer;--> statement-breakpoint
ALTER TABLE "source_document" ADD COLUMN "verification_note" text;--> statement-breakpoint
CREATE UNIQUE INDEX "uq_source_document_content_sha256" ON "source_document" USING btree ("content_sha256") WHERE "source_document"."content_sha256" IS NOT NULL;