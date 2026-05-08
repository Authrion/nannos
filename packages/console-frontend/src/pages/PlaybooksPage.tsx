import { useState, useCallback } from 'react';
import { useSearchParams } from 'react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BookOpen,
  Save,
  Loader2,
  Plus,
  Trash2,
  Users,
  User as UserIcon,
  Pencil,
  Bot,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  getPlaybookApiV1PlaybooksAgentsAgentNameGetOptions,
  getPlaybookApiV1PlaybooksAgentsAgentNameGetQueryKey,
  listSkillsApiV1PlaybooksAgentsAgentNameSkillsGetOptions,
  listSkillsApiV1PlaybooksAgentsAgentNameSkillsGetQueryKey,
  getSkillApiV1PlaybooksAgentsAgentNameSkillsSkillNameGetOptions,
  updatePlaybookApiV1PlaybooksAgentsAgentNameScopePutMutation,
  createSkillApiV1PlaybooksAgentsAgentNameSkillsScopePostMutation,
  updateSkillApiV1PlaybooksAgentsAgentNameSkillsScopeSkillNamePutMutation,
  deleteSkillApiV1PlaybooksAgentsAgentNameSkillsScopeSkillNameDeleteMutation,
  consoleListSubAgentsOptions,
  listMyGroupsApiV1GroupsGetOptions,
} from '@/api/generated/@tanstack/react-query.gen';
import type { SkillSummary } from '@/api/generated/types.gen';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from '@/components/ui/sheet';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

type TabId = 'playbook' | 'skills';

/** "personal" or a group ID string */
type ScopeSelection = string;
const PERSONAL_SCOPE = 'personal';

const tabs: { id: TabId; label: string; icon: typeof BookOpen }[] = [
  { id: 'playbook', label: 'AGENTS.md', icon: BookOpen },
  { id: 'skills', label: 'Skills', icon: BookOpen },
];

export function PlaybooksPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  // Derive state from URL search params (with defaults)
  const activeTab = (searchParams.get('tab') as TabId) || 'playbook';
  const selectedAgent = searchParams.get('agent') || 'orchestrator';
  const selectedScope: ScopeSelection = searchParams.get('scope') || PERSONAL_SCOPE;
  const [editedContent, setEditedContent] = useState<string | null>(null);

  /** Update one or more search params while preserving the rest */
  const updateParams = useCallback(
    (updates: Record<string, string>) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(updates)) {
          // Remove params that match their defaults to keep URLs clean
          if (
            (k === 'tab' && v === 'playbook') ||
            (k === 'agent' && v === 'orchestrator') ||
            (k === 'scope' && v === PERSONAL_SCOPE)
          ) {
            next.delete(k);
          } else {
            next.set(k, v);
          }
        }
        return next;
      }, { replace: true });
    },
    [setSearchParams]
  );

  // Skill state
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newSkillName, setNewSkillName] = useState('');
  const [newSkillDescription, setNewSkillDescription] = useState('');
  const [newSkillContent, setNewSkillContent] = useState('');

  // Skill editor sheet state
  const [editingSkill, setEditingSkill] = useState<SkillSummary | null>(null);

  // Delete confirmation state
  const [deletingSkill, setDeletingSkill] = useState<SkillSummary | null>(null);

  // Derived scope info
  const isPersonalScope = selectedScope === PERSONAL_SCOPE;
  const apiScope = isPersonalScope ? 'personal' : 'group';
  const groupIdParam = isPersonalScope ? undefined : selectedScope;

  const handleAgentChange = (agent: string) => {
    updateParams({ agent });
    setEditedContent(null);
  };

  const handleScopeChange = (scope: ScopeSelection) => {
    updateParams({ scope });
    setEditedContent(null);
  };

  // Fetch available sub-agents for the agent selector
  const { data: subAgentsData } = useQuery({
    ...consoleListSubAgentsOptions(),
  });

  // Fetch user's groups
  const { data: myGroupsData } = useQuery(listMyGroupsApiV1GroupsGetOptions());
  const groups = Array.isArray(myGroupsData) ? myGroupsData : [];

  const selectedGroupName = groups.find((g) => String(g.id) === selectedScope)?.name;

  const agentNames = [
    'orchestrator',
    ...(subAgentsData?.items?.map((a) => a.name).filter(Boolean) as string[] ?? []),
  ];

  // Fetch playbook (AGENTS.md) for the selected agent — aggregates all scopes
  const { data: playbookData, isLoading: playbookLoading } = useQuery({
    ...getPlaybookApiV1PlaybooksAgentsAgentNameGetOptions({
      path: { agent_name: selectedAgent },
    }),
  });

  // Fetch skills list — aggregates personal + all groups
  const { data: skillsData, isLoading: skillsLoading } = useQuery({
    ...listSkillsApiV1PlaybooksAgentsAgentNameSkillsGetOptions({
      path: { agent_name: selectedAgent },
    }),
  });

  // Derive display values — single editor for the active scope
  const serverContent = isPersonalScope
    ? playbookData?.personal?.content ?? ''
    : playbookData?.groups?.find((g) => g.group_id === selectedScope)?.content ?? '';
  const displayContent = editedContent ?? serverContent;
  const hasChanges = editedContent !== null;

  // Filter skills to only the active scope
  const allSkills = skillsData?.items ?? [];
  const scopeSkills = isPersonalScope
    ? allSkills.filter((s) => s.scope === 'personal')
    : allSkills.filter((s) => s.scope === 'group' && s.group_id === selectedScope);

  // Mutations
  const invalidatePlaybook = () =>
    queryClient.invalidateQueries({
      queryKey: getPlaybookApiV1PlaybooksAgentsAgentNameGetQueryKey({
        path: { agent_name: selectedAgent },
      }),
    });

  const invalidateSkills = () =>
    queryClient.invalidateQueries({
      queryKey: listSkillsApiV1PlaybooksAgentsAgentNameSkillsGetQueryKey({
        path: { agent_name: selectedAgent },
      }),
    });

  const updatePlaybookMutation = useMutation({
    ...updatePlaybookApiV1PlaybooksAgentsAgentNameScopePutMutation(),
    onSuccess: () => {
      toast.success('Playbook saved');
      invalidatePlaybook();
      setEditedContent(null);
    },
    onError: () => toast.error('Failed to save playbook'),
  });

  const createSkillMutation = useMutation({
    ...createSkillApiV1PlaybooksAgentsAgentNameSkillsScopePostMutation(),
    onSuccess: () => {
      toast.success('Skill created');
      invalidateSkills();
      setShowCreateDialog(false);
      setNewSkillName('');
      setNewSkillDescription('');
      setNewSkillContent('');
    },
    onError: () => toast.error('Failed to create skill'),
  });

  const deleteSkillMutation = useMutation({
    ...deleteSkillApiV1PlaybooksAgentsAgentNameSkillsScopeSkillNameDeleteMutation(),
    onSuccess: () => {
      toast.success('Skill deleted');
      invalidateSkills();
      setDeletingSkill(null);
      setEditingSkill(null);
    },
    onError: () => toast.error('Failed to delete skill'),
  });

  const handleSavePlaybook = () => {
    updatePlaybookMutation.mutate({
      path: { agent_name: selectedAgent, scope: apiScope },
      query: { group_id: groupIdParam },
      body: { content: displayContent },
    });
  };

  const handleCreateSkill = () => {
    if (!newSkillName.trim()) {
      toast.error('Skill name is required');
      return;
    }
    // Validate name per SKILL.md spec
    if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/.test(newSkillName)) {
      toast.error('Name must be lowercase letters, numbers, and hyphens only (no leading/trailing hyphens)');
      return;
    }
    if (newSkillName.includes('--')) {
      toast.error('Name must not contain consecutive hyphens (--)');
      return;
    }
    createSkillMutation.mutate({
      path: { agent_name: selectedAgent, scope: apiScope },
      query: { group_id: groupIdParam },
      body: { name: newSkillName, description: newSkillDescription, content: newSkillContent } as any,
    });
  };

  const handleConfirmDeleteSkill = () => {
    if (!deletingSkill) return;
    deleteSkillMutation.mutate({
      path: {
        agent_name: selectedAgent,
        scope: deletingSkill.scope,
        skill_name: deletingSkill.name,
      },
      query: { group_id: deletingSkill.scope === 'group' ? groupIdParam : undefined },
    });
  };

  const scopeLabel = isPersonalScope ? 'Personal' : selectedGroupName ?? 'Group';

  return (
    <div className="flex flex-col gap-6 p-4 max-w-5xl">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Playbooks</h1>
        <p className="text-sm text-muted-foreground">
          Configure agent behavior with AGENTS.md playbooks and workflow skills
        </p>
      </div>

      {/* Context Bar — agent + scope selectors */}
      <Card className="bg-muted/30">
        <CardContent className="flex flex-wrap items-center gap-x-8 gap-y-3 py-3 px-4">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-muted-foreground" />
            <Label className="text-sm font-medium text-muted-foreground">Agent</Label>
            <Select value={selectedAgent} onValueChange={handleAgentChange}>
              <SelectTrigger className="w-[220px] bg-background">
                <SelectValue placeholder="Select agent" />
              </SelectTrigger>
              <SelectContent>
                {agentNames.map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Separator orientation="vertical" className="h-6 hidden sm:block" />
          <div className="flex items-center gap-2">
            {isPersonalScope ? (
              <UserIcon className="h-4 w-4 text-muted-foreground" />
            ) : (
              <Users className="h-4 w-4 text-muted-foreground" />
            )}
            <Label className="text-sm font-medium text-muted-foreground">Scope</Label>
            <Select value={selectedScope} onValueChange={handleScopeChange}>
              <SelectTrigger className="w-[220px] bg-background">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={PERSONAL_SCOPE}>
                  Personal
                </SelectItem>
                {groups.map((g) => (
                  <SelectItem key={g.id} value={String(g.id)}>
                    {g.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <div className="flex gap-1 border-b">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => updateParams({ tab: tab.id })}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === tab.id
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground hover:border-muted-foreground/50'
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* ============ AGENTS.md Tab ============ */}
      {activeTab === 'playbook' && (
        <div className="flex flex-col gap-6">
          {playbookLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <Card>
              <CardHeader className="flex flex-row items-center gap-2 pb-2">
                {isPersonalScope ? (
                  <UserIcon className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <Users className="h-4 w-4 text-muted-foreground" />
                )}
                <div className="flex-1">
                  <span className="font-medium">{scopeLabel} Playbook</span>
                  <span className="text-xs text-muted-foreground ml-2">
                    for <code className="bg-muted px-1 rounded text-xs">{selectedAgent}</code>
                  </span>
                </div>
                <Badge variant={isPersonalScope ? 'secondary' : 'outline'} className="text-xs">
                  {isPersonalScope ? 'Only you' : 'Shared'}
                </Badge>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <p className="text-xs text-muted-foreground">
                  {isPersonalScope
                    ? 'Your personal instructions. These override group playbooks when they conflict.'
                    : `Applies to all members of ${selectedGroupName ?? 'this group'}. Requires write role.`}
                </p>
                <Textarea
                  value={displayContent}
                  onChange={(e) => setEditedContent(e.target.value)}
                  placeholder={
                    isPersonalScope
                      ? '# AGENTS.md\n\n## Preferences\n\n- Always respond in bullet points\n- Use formal tone'
                      : '# AGENTS.md\n\n## Team Standards\n\n- Follow company coding guidelines\n- Always include links to sources'
                  }
                  className="min-h-[250px] font-mono text-sm"
                />
                <div className="flex items-center justify-end gap-2">
                  {hasChanges && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditedContent(null)}
                    >
                      Discard
                    </Button>
                  )}
                  <Button
                    onClick={handleSavePlaybook}
                    disabled={!hasChanges || updatePlaybookMutation.isPending}
                    size="sm"
                  >
                    {updatePlaybookMutation.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Save className="mr-2 h-4 w-4" />
                    )}
                    Save
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ============ Skills Tab ============ */}
      {activeTab === 'skills' && (
        <div className="flex flex-col gap-4">
          {/* Toolbar */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {isPersonalScope
                ? 'Your personal skills'
                : `Shared skills for ${selectedGroupName ?? 'this group'}`}
            </p>
            <Button size="sm" onClick={() => setShowCreateDialog(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New Skill
            </Button>
          </div>

          {/* Skills list */}
          {skillsLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : scopeSkills.length === 0 ? (
            <div className="text-center text-muted-foreground py-12">
              <BookOpen className="mx-auto h-8 w-8 mb-2 opacity-50" />
              <p>No {isPersonalScope ? 'personal' : 'group'} skills configured yet.</p>
              <p className="text-sm mt-1">
                Skills are complex workflows that agents can fetch on-demand.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {scopeSkills.map((skill) => (
                <Card
                  key={`${skill.scope}-${skill.name}`}
                  className="cursor-pointer hover:bg-accent/50 transition-colors"
                  onClick={() => setEditingSkill(skill)}
                >
                  <CardContent className="flex items-center justify-between py-3 px-4">
                    <div className="flex items-center gap-3 min-w-0">
                      <BookOpen className="h-4 w-4 text-muted-foreground shrink-0" />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm font-medium">{skill.name}</span>
                          {skill.title && skill.title !== skill.name && (
                            <span className="text-muted-foreground text-sm truncate">
                              — {skill.title}
                            </span>
                          )}
                        </div>
                        {skill.description && (
                          <p className="text-xs text-muted-foreground truncate">
                            {skill.description}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingSkill(skill);
                        }}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeletingSkill(skill);
                        }}
                        className="text-destructive hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ============ Skill Editor Sheet ============ */}
      {editingSkill && (
        <SkillEditorSheet
          key={`${editingSkill.scope}:${editingSkill.name}`}
          skill={editingSkill}
          agentName={selectedAgent}
          groupQueryParam={groupIdParam}
          scopeLabel={scopeLabel}
          onSaved={() => {
            invalidateSkills();
            setEditingSkill(null);
          }}
          onDelete={(skill) => setDeletingSkill(skill)}
          onClose={() => setEditingSkill(null)}
        />
      )}

      {/* ============ Create Skill Dialog ============ */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              Create {scopeLabel} Skill
              <span className="text-muted-foreground font-normal text-sm ml-2">
                for <code className="bg-muted px-1 rounded text-xs">{selectedAgent}</code>
              </span>
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-2">
            <div>
              <Label className="text-sm">Name (identifier)</Label>
              <Input
                value={newSkillName}
                onChange={(e) => setNewSkillName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                placeholder="incident-triage"
                className="mt-1 font-mono"
                maxLength={64}
              />
              <p className="text-xs text-muted-foreground mt-1">
                Lowercase letters, numbers, and hyphens only (max 64 chars)
              </p>
            </div>
            <div>
              <Label className="text-sm">Description</Label>
              <Textarea
                value={newSkillDescription}
                onChange={(e) => setNewSkillDescription(e.target.value)}
                placeholder="Triage production incidents step by step. Use when there is an active incident that needs investigation."
                className="min-h-[60px] text-sm mt-1"
                maxLength={1024}
              />
              <p className="text-xs text-muted-foreground mt-1">
                Describe what the skill does and when to use it (shown in skill index)
              </p>
            </div>
            <div>
              <Label className="text-sm">Instructions (Markdown)</Label>
              <Textarea
                value={newSkillContent}
                onChange={(e) => setNewSkillContent(e.target.value)}
                placeholder="## Steps&#10;&#10;1. Check monitoring dashboards&#10;2. Identify affected services&#10;3. Open incident channel"
                className="min-h-[180px] font-mono text-sm mt-1"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateSkill} disabled={createSkillMutation.isPending}>
              {createSkillMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Plus className="mr-2 h-4 w-4" />
              )}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ============ Delete Confirmation Dialog ============ */}
      <AlertDialog open={!!deletingSkill} onOpenChange={(open) => !open && setDeletingSkill(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete skill &quot;{deletingSkill?.name}&quot;?</AlertDialogTitle>
            <AlertDialogDescription>
              {deletingSkill?.scope === 'group'
                ? 'This is a group skill — deleting it will affect all group members. This action cannot be undone.'
                : 'This action cannot be undone.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDeleteSkill}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteSkillMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="mr-2 h-4 w-4" />
              )}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────── */
/*  Skill Editor Sheet                                        */
/* ─────────────────────────────────────────────────────────── */

function SkillEditorSheet({
  skill,
  agentName,
  groupQueryParam,
  scopeLabel,
  onSaved,
  onDelete,
  onClose,
}: {
  skill: SkillSummary;
  agentName: string;
  groupQueryParam: string | undefined;
  scopeLabel: string;
  onSaved: () => void;
  onDelete: (skill: SkillSummary) => void;
  onClose: () => void;
}) {
  const [editedContent, setEditedContent] = useState<string | null>(null);

  const { data: skillDetail, isLoading: isLoadingContent } = useQuery({
    ...getSkillApiV1PlaybooksAgentsAgentNameSkillsSkillNameGetOptions({
      path: { agent_name: agentName, skill_name: skill.name },
      query: {
        scope: skill.scope,
        group_id: skill.scope === 'group' ? groupQueryParam : undefined,
      },
    }),
  });

  const serverContent = skillDetail?.content ?? '';
  const displayContent = editedContent ?? serverContent;
  const hasChanges = editedContent !== null;

  const updateMutation = useMutation({
    ...updateSkillApiV1PlaybooksAgentsAgentNameSkillsScopeSkillNamePutMutation(),
    onSuccess: () => {
      toast.success('Skill updated');
      onSaved();
    },
    onError: () => toast.error('Failed to update skill'),
  });

  const handleSave = () => {
    updateMutation.mutate({
      path: { agent_name: agentName, scope: skill.scope, skill_name: skill.name },
      query: { group_id: skill.scope === 'group' ? groupQueryParam : undefined },
      body: { content: displayContent },
    });
  };

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="sm:max-w-xl w-full flex flex-col">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            <span className="font-mono">{skill.name}</span>
          </SheetTitle>
          <SheetDescription>
            {scopeLabel} skill for{' '}
            <code className="text-xs bg-muted px-1 rounded">{agentName}</code>
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-4">
          {isLoadingContent ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <Textarea
              value={displayContent}
              onChange={(e) => setEditedContent(e.target.value)}
              className="min-h-[400px] h-full font-mono text-sm resize-none"
              placeholder="# Skill Content&#10;&#10;Describe the skill workflow..."
            />
          )}
        </div>

        <SheetFooter className="flex-row justify-between border-t pt-4 px-4">
          <Button
            variant="destructive"
            size="sm"
            onClick={() => onDelete(skill)}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </Button>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSave} disabled={!hasChanges || updateMutation.isPending}>
              {updateMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              Save
            </Button>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
