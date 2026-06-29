import { Router } from "express";
import { db, presetsTable } from "@workspace/db";
import { eq } from "drizzle-orm";
import {
  CreatePresetBody,
  UpdatePresetBody,
  GetPresetParams,
  UpdatePresetParams,
  DeletePresetParams,
} from "@workspace/api-zod";

const router = Router();

function rowToPreset(row: typeof presetsTable.$inferSelect) {
  return {
    id: row.id,
    name: row.name,
    isDefault: row.isDefault,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
    params: {
      pitchSemitones: row.pitchSemitones,
      formantShift: row.formantShift,
      roboticAmount: row.roboticAmount,
      noiseGateDb: row.noiseGateDb,
      volumeOut: row.volumeOut,
      highpassFreq: row.highpassFreq,
      lowpassFreq: row.lowpassFreq,
      compressorThreshold: row.compressorThreshold,
      compressorRatio: row.compressorRatio,
    },
  };
}

router.get("/presets", async (req, res): Promise<void> => {
  try {
    const rows = await db.select().from(presetsTable).orderBy(presetsTable.id);
    res.json(rows.map(rowToPreset));
  } catch (err) {
    req.log.error({ err }, "Failed to list presets");
    res.status(500).json({ error: "Failed to list presets" });
  }
});

router.post("/presets", async (req, res): Promise<void> => {
  const parsed = CreatePresetBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const { name, params } = parsed.data;
  try {
    const [row] = await db
      .insert(presetsTable)
      .values({
        name,
        pitchSemitones: params.pitchSemitones,
        formantShift: params.formantShift,
        roboticAmount: params.roboticAmount,
        noiseGateDb: params.noiseGateDb,
        volumeOut: params.volumeOut,
        highpassFreq: params.highpassFreq,
        lowpassFreq: params.lowpassFreq,
        compressorThreshold: params.compressorThreshold,
        compressorRatio: params.compressorRatio,
      })
      .returning();
    res.status(201).json(rowToPreset(row));
  } catch (err) {
    req.log.error({ err }, "Failed to create preset");
    res.status(500).json({ error: "Failed to create preset" });
  }
});

router.get("/presets/:id", async (req, res): Promise<void> => {
  const parsed = GetPresetParams.safeParse({ id: Number(req.params.id) });
  if (!parsed.success) {
    res.status(400).json({ error: "Invalid id" });
    return;
  }
  try {
    const rows = await db
      .select()
      .from(presetsTable)
      .where(eq(presetsTable.id, parsed.data.id));
    if (!rows.length) {
      res.status(404).json({ error: "Preset not found" });
      return;
    }
    res.json(rowToPreset(rows[0]));
  } catch (err) {
    req.log.error({ err }, "Failed to get preset");
    res.status(500).json({ error: "Failed to get preset" });
  }
});

router.patch("/presets/:id", async (req, res): Promise<void> => {
  const idParsed = UpdatePresetParams.safeParse({ id: Number(req.params.id) });
  if (!idParsed.success) {
    res.status(400).json({ error: "Invalid id" });
    return;
  }
  const bodyParsed = UpdatePresetBody.safeParse(req.body);
  if (!bodyParsed.success) {
    res.status(400).json({ error: bodyParsed.error.message });
    return;
  }
  const { name, params } = bodyParsed.data;
  try {
    const updates: Partial<typeof presetsTable.$inferInsert> = {
      updatedAt: new Date(),
    };
    if (name !== undefined) updates.name = name;
    if (params !== undefined) {
      updates.pitchSemitones = params.pitchSemitones;
      updates.formantShift = params.formantShift;
      updates.roboticAmount = params.roboticAmount;
      updates.noiseGateDb = params.noiseGateDb;
      updates.volumeOut = params.volumeOut;
      updates.highpassFreq = params.highpassFreq;
      updates.lowpassFreq = params.lowpassFreq;
      updates.compressorThreshold = params.compressorThreshold;
      updates.compressorRatio = params.compressorRatio;
    }
    const rows = await db
      .update(presetsTable)
      .set(updates)
      .where(eq(presetsTable.id, idParsed.data.id))
      .returning();
    if (!rows.length) {
      res.status(404).json({ error: "Preset not found" });
      return;
    }
    res.json(rowToPreset(rows[0]));
  } catch (err) {
    req.log.error({ err }, "Failed to update preset");
    res.status(500).json({ error: "Failed to update preset" });
  }
});

router.delete("/presets/:id", async (req, res): Promise<void> => {
  const parsed = DeletePresetParams.safeParse({ id: Number(req.params.id) });
  if (!parsed.success) {
    res.status(400).json({ error: "Invalid id" });
    return;
  }
  try {
    const rows = await db
      .delete(presetsTable)
      .where(eq(presetsTable.id, parsed.data.id))
      .returning();
    if (!rows.length) {
      res.status(404).json({ error: "Preset not found" });
      return;
    }
    res.status(204).send();
  } catch (err) {
    req.log.error({ err }, "Failed to delete preset");
    res.status(500).json({ error: "Failed to delete preset" });
  }
});

export default router;
