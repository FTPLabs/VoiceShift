import { useState } from "react";
import { useListPresets, useCreatePreset, useDeletePreset, getListPresetsQueryKey } from "@workspace/api-client-react";
import { VoiceParams, DEFAULT_PARAMS } from "../audio/VoiceProcessor";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Trash2, Save } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface PresetPanelProps {
  currentParams: VoiceParams;
  onLoadPreset: (params: VoiceParams) => void;
}

export function PresetPanel({ currentParams, onLoadPreset }: PresetPanelProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { data: presets = [], isLoading } = useListPresets();
  const createMut = useCreatePreset();
  const deleteMut = useDeletePreset();

  const [newPresetName, setNewPresetName] = useState("");

  const handleSave = () => {
    if (!newPresetName.trim()) return;
    createMut.mutate(
      { data: { name: newPresetName, params: currentParams } },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListPresetsQueryKey() });
          setNewPresetName("");
          toast({ title: "Preset saved", description: `Saved "${newPresetName}"` });
        },
        onError: () => {
          toast({ title: "Error", description: "Failed to save preset", variant: "destructive" });
        }
      }
    );
  };

  const handleDelete = (id: number, name: string) => {
    deleteMut.mutate(
      { id },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListPresetsQueryKey() });
          toast({ title: "Preset deleted", description: `Deleted "${name}"` });
        }
      }
    );
  };

  const fallbackPresets = [
    { name: "Default", params: DEFAULT_PARAMS },
    { name: "Deep Voice", params: { ...DEFAULT_PARAMS, pitchSemitones: -4, formantShift: 0.8 } },
    { name: "High Voice", params: { ...DEFAULT_PARAMS, pitchSemitones: 5, formantShift: 1.2 } },
    { name: "Robot", params: { ...DEFAULT_PARAMS, roboticAmount: 1.0 } }
  ];

  const displayPresets = presets.length > 0 ? presets : fallbackPresets;

  return (
    <Card className="border-border bg-card">
      <CardHeader className="py-4">
        <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Presets</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Input 
            placeholder="New preset name..." 
            value={newPresetName}
            onChange={(e) => setNewPresetName(e.target.value)}
            className="text-sm"
          />
          <Button size="icon" onClick={handleSave} disabled={!newPresetName.trim() || createMut.isPending}>
            <Save className="w-4 h-4" />
          </Button>
        </div>

        <div className="space-y-2">
          {isLoading && presets.length === 0 ? (
            <div className="text-sm text-muted-foreground">Loading presets...</div>
          ) : (
            displayPresets.map((p, i) => (
              <div key={'id' in p ? (p as { id: number }).id : `fallback-${i}`} className="flex items-center justify-between group rounded-md bg-muted/20 p-2 hover:bg-muted/40 transition-colors">
                <button 
                  className="text-sm flex-1 text-left hover:text-primary transition-colors font-medium truncate"
                  onClick={() => onLoadPreset(p.params)}
                >
                  {p.name}
                </button>
                {'id' in p && (
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    className="opacity-0 group-hover:opacity-100 transition-opacity h-8 w-8 text-destructive"
                    onClick={() => handleDelete((p as any).id, p.name)}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                )}
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
