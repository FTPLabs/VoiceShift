import { pgTable, serial, text, real, boolean, timestamp } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const presetsTable = pgTable("presets", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  isDefault: boolean("is_default").notNull().default(false),
  pitchSemitones: real("pitch_semitones").notNull().default(0),
  formantShift: real("formant_shift").notNull().default(1.0),
  roboticAmount: real("robotic_amount").notNull().default(0.0),
  noiseGateDb: real("noise_gate_db").notNull().default(-50),
  volumeOut: real("volume_out").notNull().default(1.0),
  highpassFreq: real("highpass_freq").notNull().default(80),
  lowpassFreq: real("lowpass_freq").notNull().default(16000),
  compressorThreshold: real("compressor_threshold").notNull().default(-24),
  compressorRatio: real("compressor_ratio").notNull().default(4),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});

export const insertPresetSchema = createInsertSchema(presetsTable).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export type InsertPreset = z.infer<typeof insertPresetSchema>;
export type Preset = typeof presetsTable.$inferSelect;
