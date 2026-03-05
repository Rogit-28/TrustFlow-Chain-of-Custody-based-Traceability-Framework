import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useToast } from '../components/ui/toast';
import { Shield, Network, Activity, Search, ShieldAlert, CheckCircle2, XCircle, FileText, Share2, Info, Maximize2, Minimize2, Crosshair, CornerDownRight } from 'lucide-react';
import { Network as VisNetwork } from 'vis-network';
import { DataSet } from 'vis-data';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

export default function AdminDashboard() {
    const [peers, setPeers] = useState([]);
    const [auditResult, setAuditResult] = useState(null);
    const [isVerifying, setIsVerifying] = useState(false);
    const [activeGraph, setActiveGraph] = useState('my');
    const [documents, setDocuments] = useState([]);
    const [selectedDoc, setSelectedDoc] = useState('');
    const [selectedDocName, setSelectedDocName] = useState('');
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [pathStatus, setPathStatus] = useState(null);
    const [pathModeEnabled, setPathModeEnabled] = useState(false);
    const [pathComputeMode, setPathComputeMode] = useState('shortest');
    const [pathSource, setPathSource] = useState(null);       // { id, label }
    const [pathTarget, setPathTarget] = useState(null);       // { id, label }
    const [isPathLoading, setIsPathLoading] = useState(false);

    // File Trace search state
    const [fileSearchQuery, setFileSearchQuery] = useState('');
    const [showFilePicker, setShowFilePicker] = useState(false);
    const fileSearchRef = useRef(null);

    const graphRef = useRef(null);
    const networkRef = useRef(null);
    const nodesDatasetRef = useRef(null);
    const edgesDatasetRef = useRef(null);
    const baseGraphRef = useRef({ nodes: [], edges: [] });
    const pathOverlayRef = useRef({ nodeIds: new Set(), edgeKeys: new Set() });
    const nodeMetaRef = useRef(new Map());    // id -> { label, ownerUsername }
    const pathModeRef = useRef(false);
    const pathSourceRef = useRef(null);
    const pathTargetRef = useRef(null);
    const toast = useToast();

    const edgeKey = (from, to) => `${from}->${to}`;

    // ── Visual style application (updates DataSet in-place, no setData) ──

    const applyVisualOverlay = useCallback(() => {
        const nodesDs = nodesDatasetRef.current;
        const edgesDs = edgesDatasetRef.current;
        if (!nodesDs || !edgesDs) return;

        const { nodes: baseNodes, edges: baseEdges } = baseGraphRef.current;
        const pathNodeSet = pathOverlayRef.current.nodeIds;
        const pathEdgeSet = pathOverlayRef.current.edgeKeys;
        const hasPath = pathNodeSet.size > 0;

        const pathHighlight = {
            border: '#f59e0b',
            bg: 'rgba(245,158,11,0.15)',
            font: '#fbbf24',
            edge: 'rgba(245,158,11,0.9)',
        };

        const sourceId = pathSourceRef.current?.id;
        const targetId = pathTargetRef.current?.id;

        // Batch node updates
        const nodeUpdates = baseNodes.map((base) => {
            // Path highlight takes priority
            if (hasPath && pathNodeSet.has(base.id)) {
                // Source node gets distinct red, target gets amber
                if (base.id === sourceId) {
                    return {
                        id: base.id,
                        color: {
                            border: '#ff073a',
                            background: 'rgba(255,7,58,0.2)',
                            highlight: { background: 'rgba(255,7,58,0.24)', border: '#ff073a' },
                            hover: { background: 'rgba(255,7,58,0.22)', border: '#ff073a' },
                        },
                        font: { ...base.font, color: '#ff8da2' },
                        borderWidth: 3,
                        shadow: { enabled: true, color: 'rgba(255,7,58,0.35)', size: 18 },
                    };
                }
                if (base.id === targetId) {
                    return {
                        id: base.id,
                        color: {
                            border: '#10b981',
                            background: 'rgba(16,185,129,0.15)',
                            highlight: { background: 'rgba(16,185,129,0.2)', border: '#10b981' },
                            hover: { background: 'rgba(16,185,129,0.18)', border: '#10b981' },
                        },
                        font: { ...base.font, color: '#6ee7b7' },
                        borderWidth: 3,
                        shadow: { enabled: true, color: 'rgba(16,185,129,0.35)', size: 18 },
                    };
                }
                return {
                    id: base.id,
                    color: {
                        border: pathHighlight.border,
                        background: pathHighlight.bg,
                        highlight: { background: pathHighlight.bg, border: pathHighlight.border },
                        hover: { background: pathHighlight.bg, border: pathHighlight.border },
                    },
                    font: { ...base.font, color: pathHighlight.font },
                    borderWidth: 3,
                    shadow: { enabled: true, color: 'rgba(245,158,11,0.35)', size: 18 },
                };
            }

            // Source/target markers without active path
            if (base.id === sourceId) {
                return {
                    id: base.id,
                    color: {
                        border: '#ff073a',
                        background: 'rgba(255,7,58,0.15)',
                        highlight: { background: 'rgba(255,7,58,0.2)', border: '#ff073a' },
                        hover: { background: 'rgba(255,7,58,0.18)', border: '#ff073a' },
                    },
                    font: { ...base.font, color: '#ff8da2' },
                    borderWidth: 3,
                    shadow: base.shadow,
                };
            }
            if (base.id === targetId) {
                return {
                    id: base.id,
                    color: {
                        border: '#10b981',
                        background: 'rgba(16,185,129,0.12)',
                        highlight: { background: 'rgba(16,185,129,0.18)', border: '#10b981' },
                        hover: { background: 'rgba(16,185,129,0.15)', border: '#10b981' },
                    },
                    font: { ...base.font, color: '#6ee7b7' },
                    borderWidth: 3,
                    shadow: base.shadow,
                };
            }

            // Dim non-path nodes when a path is active
            if (hasPath) {
                return {
                    id: base.id,
                    color: {
                        border: 'rgba(255,255,255,0.06)',
                        background: 'rgba(255,255,255,0.015)',
                        highlight: { background: 'rgba(255,255,255,0.03)', border: 'rgba(255,255,255,0.1)' },
                        hover: { background: 'rgba(255,255,255,0.03)', border: 'rgba(255,255,255,0.1)' },
                    },
                    font: { ...base.font, color: '#374151' },
                    borderWidth: base.borderWidth,
                    shadow: { enabled: false },
                };
            }

            // Default: restore base style
            return {
                id: base.id,
                color: base.color,
                font: base.font,
                borderWidth: base.borderWidth,
                shadow: base.shadow,
            };
        });

        // Batch edge updates
        const edgeUpdates = baseEdges.map((base) => {
            if (hasPath && pathEdgeSet.has(edgeKey(base.from, base.to))) {
                return {
                    id: base.id,
                    color: { color: pathHighlight.edge, highlight: pathHighlight.edge, hover: pathHighlight.edge },
                    width: 3,
                };
            }
            if (hasPath) {
                return {
                    id: base.id,
                    color: { color: 'rgba(255,255,255,0.03)', highlight: 'rgba(255,255,255,0.04)', hover: 'rgba(255,255,255,0.04)' },
                    width: 0.7,
                };
            }
            return {
                id: base.id,
                color: base.color,
                width: base.width,
            };
        });

        nodesDs.update(nodeUpdates);
        edgesDs.update(edgeUpdates);
    }, []);

    // ── Path resolution ──

    const resolvePathFromApi = useCallback(async (source, target, computeMode) => {
        if (!source || !target) return;

        setIsPathLoading(true);
        try {
            const params = {
                source: source.id,
                target: target.id,
                mode: computeMode,
                scope: activeGraph === 'my' ? 'my' : 'file',
                max_paths: computeMode === 'all' ? 50 : 1,
                max_depth: 24,
            };
            if (activeGraph === 'file') {
                params.document_id = selectedDoc;
            }

            const res = await axios.get('/admin/graph/path', { params });
            const payload = res.data;
            const allPathNodes = new Set();
            const allPathEdges = new Set();

            payload.paths.forEach((p) => {
                p.nodes.forEach((n) => allPathNodes.add(n));
                p.edges.forEach((e) => allPathEdges.add(edgeKey(e.from_node, e.to_node)));
            });

            pathOverlayRef.current = { nodeIds: allPathNodes, edgeKeys: allPathEdges };

            if (payload.path_count > 0) {
                const shortestPath = payload.paths.reduce((best, current) => {
                    if (!best) return current;
                    return current.nodes.length < best.nodes.length ? current : best;
                }, null);
                setPathStatus({
                    found: true,
                    mode: payload.mode,
                    pathCount: payload.path_count,
                    truncated: payload.truncated,
                    hops: shortestPath ? Math.max(shortestPath.nodes.length - 1, 0) : 0,
                });
            } else {
                setPathStatus({
                    found: false,
                    mode: payload.mode,
                    pathCount: 0,
                    truncated: payload.truncated,
                    hops: 0,
                });
            }

            applyVisualOverlay();
        } catch (err) {
            pathOverlayRef.current = { nodeIds: new Set(), edgeKeys: new Set() };
            setPathStatus(null);
            applyVisualOverlay();
            toast({
                title: 'Path lookup failed',
                description: err.response?.data?.detail || err.message,
                type: 'error',
            });
        } finally {
            setIsPathLoading(false);
        }
    }, [activeGraph, selectedDoc, applyVisualOverlay, toast]);

    // ── Click-to-assign source/target in path mode ──

    const handleNodeClick = useCallback((nodeId) => {
        if (!pathModeRef.current) return;
        if (!nodeId) return;

        const meta = nodeMetaRef.current.get(nodeId);
        const nodeInfo = meta
            ? { id: nodeId, label: `${meta.ownerUsername} · ${nodeId.substring(0, 8)}` }
            : { id: nodeId, label: nodeId.substring(0, 12) };

        const currentSource = pathSourceRef.current;
        const currentTarget = pathTargetRef.current;

        // If clicking the same node that's already source, remove it
        if (currentSource?.id === nodeId) {
            pathSourceRef.current = null;
            setPathSource(null);
            pathOverlayRef.current = { nodeIds: new Set(), edgeKeys: new Set() };
            setPathStatus(null);
            applyVisualOverlay();
            return;
        }
        // If clicking the same node that's already target, remove it
        if (currentTarget?.id === nodeId) {
            pathTargetRef.current = null;
            setPathTarget(null);
            pathOverlayRef.current = { nodeIds: new Set(), edgeKeys: new Set() };
            setPathStatus(null);
            applyVisualOverlay();
            return;
        }

        // If no source yet, assign as source
        if (!currentSource) {
            pathSourceRef.current = nodeInfo;
            setPathSource(nodeInfo);
            applyVisualOverlay();
            return;
        }

        // If source exists but no target, assign as target and resolve
        if (!currentTarget) {
            pathTargetRef.current = nodeInfo;
            setPathTarget(nodeInfo);
            applyVisualOverlay();
            resolvePathFromApi(currentSource, nodeInfo, pathComputeMode);
            return;
        }

        // Both exist: replace target and re-resolve
        pathTargetRef.current = nodeInfo;
        setPathTarget(nodeInfo);
        pathOverlayRef.current = { nodeIds: new Set(), edgeKeys: new Set() };
        applyVisualOverlay();
        resolvePathFromApi(currentSource, nodeInfo, pathComputeMode);
    }, [pathComputeMode, applyVisualOverlay, resolvePathFromApi]);

    const clearPathState = useCallback(() => {
        pathSourceRef.current = null;
        pathTargetRef.current = null;
        setPathSource(null);
        setPathTarget(null);
        pathOverlayRef.current = { nodeIds: new Set(), edgeKeys: new Set() };
        setPathStatus(null);
        applyVisualOverlay();
    }, [applyVisualOverlay]);

    const swapSourceTarget = useCallback(() => {
        const oldSource = pathSourceRef.current;
        const oldTarget = pathTargetRef.current;
        pathSourceRef.current = oldTarget;
        pathTargetRef.current = oldSource;
        setPathSource(oldTarget);
        setPathTarget(oldSource);
        pathOverlayRef.current = { nodeIds: new Set(), edgeKeys: new Set() };
        setPathStatus(null);
        applyVisualOverlay();
        if (oldTarget && oldSource) {
            resolvePathFromApi(oldTarget, oldSource, pathComputeMode);
        }
    }, [pathComputeMode, applyVisualOverlay, resolvePathFromApi]);

    // ── Data fetching ──

    const fetchPeers = async () => { try { const res = await axios.get('/admin/peers'); setPeers(res.data); } catch { } };

    const fetchDocuments = async () => {
        try {
            const res = await axios.get('/documents');
            const owned = res.data.owned || [];
            setDocuments(owned);
        } catch { }
    };

    const sharedDocs = documents.filter(d => d.share_count > 0);
    const filteredDocs = fileSearchQuery.trim()
        ? sharedDocs.filter(d => d.filename.toLowerCase().includes(fileSearchQuery.toLowerCase()))
        : sharedDocs;

    const loadGraph = async () => {
        try {
            const endpoint = activeGraph === 'my' ? '/admin/graph/me' : `/documents/${selectedDoc}/trace`;
            if (activeGraph === 'file' && !selectedDoc) return;
            const res = await axios.get(endpoint);
            const { nodes, edges } = res.data;

            // Build node metadata map for click-to-assign labels
            const metaMap = new Map();
            nodes.forEach((n) => {
                metaMap.set(n.node_hash, {
                    ownerUsername: n.owner_username,
                    filename: n.filename || '',
                });
            });
            nodeMetaRef.current = metaMap;

            const vNodes = nodes.map(n => ({
                id: n.node_hash,
                label: n.parent_hash
                    ? `${n.owner_username}\n${n.node_hash.substring(0, 6)}`
                    : `${n.owner_username}\n${n.filename ? n.filename.substring(0, 15) + '\u2026' : ''}\n${n.node_hash.substring(0, 6)}`,
                color: {
                    background: n.is_online ? 'rgba(16,185,129,0.1)' : (n.parent_hash ? 'rgba(255,255,255,0.04)' : 'rgba(255,7,58,0.08)'),
                    border: n.is_online ? '#10b981' : (n.parent_hash ? 'rgba(255,255,255,0.2)' : '#ff073a'),
                    highlight: { background: n.is_online ? 'rgba(16,185,129,0.2)' : 'rgba(255,7,58,0.15)', border: n.is_online ? '#10b981' : '#ff073a' },
                    hover: { background: n.is_online ? 'rgba(16,185,129,0.15)' : 'rgba(255,7,58,0.1)', border: n.is_online ? '#10b981' : '#ff073a' }
                },
                font: { color: n.is_online ? '#10b981' : '#999', face: 'Inter', size: 10 },
                shape: n.parent_hash ? 'dot' : 'diamond',
                size: n.parent_hash ? 12 : 22,
                shadow: { enabled: true, color: n.is_online ? 'rgba(16,185,129,0.4)' : (n.parent_hash ? 'rgba(255,255,255,0.05)' : 'rgba(255,7,58,0.3)'), size: 12 },
                borderWidth: n.parent_hash ? 1 : 2
            }));

            const vEdges = edges.map((e, i) => ({
                id: `e-${i}`,
                from: e.from,
                to: e.to,
                arrows: 'to',
                color: { color: 'rgba(255,255,255,0.08)', highlight: '#ff073a', hover: 'rgba(255,7,58,0.3)' },
                smooth: { type: 'curvedCW', roundness: 0.15 },
                width: 1
            }));

            // Store base styles for overlay calculations
            baseGraphRef.current = { nodes: vNodes, edges: vEdges };

            // Reset path state on graph reload
            pathSourceRef.current = null;
            pathTargetRef.current = null;
            setPathSource(null);
            setPathTarget(null);
            pathOverlayRef.current = { nodeIds: new Set(), edgeKeys: new Set() };
            setPathStatus(null);

            const nodesDs = new DataSet(vNodes);
            const edgesDs = new DataSet(vEdges);
            nodesDatasetRef.current = nodesDs;
            edgesDatasetRef.current = edgesDs;

            if (networkRef.current) {
                networkRef.current.setData({ nodes: nodesDs, edges: edgesDs });
            } else if (graphRef.current) {
                networkRef.current = new VisNetwork(graphRef.current, { nodes: nodesDs, edges: edgesDs }, {
                    physics: {
                        solver: 'forceAtlas2Based',
                        forceAtlas2Based: { gravitationalConstant: -50, springLength: 100 },
                        stabilization: { iterations: 150 },
                    },
                    interaction: {
                        hover: true,
                        tooltipDelay: 200,
                        multiselect: true,
                        selectConnectedEdges: false,
                        keyboard: false,
                    },
                    nodes: {
                        chosen: true,
                    },
                    edges: {
                        chosen: true,
                    },
                });
            }

            // (Re-)attach event listeners
            if (networkRef.current) {
                networkRef.current.off('click');
                networkRef.current.on('click', (params) => {
                    if (params.nodes.length === 1) {
                        handleNodeClick(params.nodes[0]);
                    }
                });
            }
        } catch { toast({ title: 'Graph load failed', type: 'error' }); }
    };

    useEffect(() => { fetchPeers(); fetchDocuments(); }, []);
    useEffect(() => { if (activeGraph === 'my' || selectedDoc) loadGraph(); }, [activeGraph, selectedDoc]);

    // Keep pathModeRef in sync
    useEffect(() => { pathModeRef.current = pathModeEnabled; }, [pathModeEnabled]);

    // Re-resolve when compute mode changes (if both endpoints set)
    useEffect(() => {
        if (pathModeEnabled && pathSourceRef.current && pathTargetRef.current) {
            resolvePathFromApi(pathSourceRef.current, pathTargetRef.current, pathComputeMode);
        }
    }, [pathComputeMode]);

    // Close file picker on outside click
    useEffect(() => {
        const handler = (e) => { if (fileSearchRef.current && !fileSearchRef.current.contains(e.target)) setShowFilePicker(false); };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const handleVerify = async () => {
        setIsVerifying(true);
        try { const res = await axios.post('/admin/verify-log'); setAuditResult(res.data); }
        catch { toast({ title: 'Verify failed', type: 'error' }); }
        finally { setIsVerifying(false); }
    };

    const selectFileForTrace = (doc) => {
        setSelectedDoc(doc.id);
        setSelectedDocName(doc.filename);
        setShowFilePicker(false);
        setFileSearchQuery('');
    };

    // ── Helpers for path mode UI ──
    const sourceLabel = pathSource ? pathSource.label : null;
    const targetLabel = pathTarget ? pathTarget.label : null;
    const pathAssignHint = !pathSource
        ? 'Click a node to set Source'
        : !pathTarget
            ? 'Click another node to set Target'
            : null;

    return (
        <div className="h-full flex flex-col">
            <div className="mb-8 flex items-center gap-3">
                <ShieldAlert className="h-6 w-6 text-red-500" />
                <div>
                    <h1 className="text-2xl font-display font-bold text-white tracking-tight">Mission Control</h1>
                    <p className="text-gray-600 text-sm mt-0.5">Network topography and forensic analysis.</p>
                </div>
            </div>

            <div className="flex flex-col gap-6 flex-1 pb-8 overflow-y-auto pr-1">
                {/* Graph */}
                <Card className={`flex flex-col w-full min-h-[500px] lg:min-h-[600px] shrink-0 transition-all duration-300 ${isFullscreen ? 'fixed inset-4 z-[100] shadow-2xl bg-black rounded-lg border border-white/[0.1]' : ''}`}>
                    <CardHeader className="border-b border-white/[0.04] pb-4">
                        <div className="flex justify-between items-center">
                            <div>
                                <CardTitle className="text-base flex items-center gap-2"><Network className="h-4 w-4 text-gray-500" /> CoC Topography</CardTitle>
                                <CardDescription>Provenance tree of all digital assets.</CardDescription>
                            </div>
                            <div className="flex items-center gap-2">
                                <Button onClick={() => setIsFullscreen(!isFullscreen)} size="sm" variant="ghost" className="px-2">
                                    {isFullscreen ? <Minimize2 className="h-4 w-4 text-gray-400" /> : <Maximize2 className="h-4 w-4 text-gray-400" />}
                                </Button>
                                <Button onClick={loadGraph} size="sm" variant="secondary">Refresh</Button>
                            </div>
                        </div>
                        <div className="flex items-center gap-1 mt-3 bg-[#050505] p-1 rounded-lg w-max border border-white/[0.04] shadow-inner">
                            <Button size="sm" variant={activeGraph === 'my' ? 'secondary' : 'ghost'} onClick={() => { setActiveGraph('my'); setSelectedDoc(''); setSelectedDocName(''); clearPathState(); }} className={`px-4 rounded-md transition-all duration-300 ${activeGraph === 'my' ? 'bg-white/[0.08] shadow-[0_2px_10px_rgba(0,0,0,0.5)] border border-white/10' : 'hover:bg-white/[0.03] text-gray-500'}`}>My Network</Button>
                            <Button size="sm" variant={activeGraph === 'file' ? 'secondary' : 'ghost'} onClick={() => { setActiveGraph('file'); setSelectedDoc(''); setSelectedDocName(''); clearPathState(); if (networkRef.current) { const emptyN = new DataSet(); const emptyE = new DataSet(); nodesDatasetRef.current = emptyN; edgesDatasetRef.current = emptyE; networkRef.current.setData({ nodes: emptyN, edges: emptyE }); } }} className={`px-4 rounded-md transition-all duration-300 ${activeGraph === 'file' ? 'bg-white/[0.08] shadow-[0_2px_10px_rgba(0,0,0,0.5)] border border-white/10' : 'hover:bg-white/[0.03] text-gray-500'}`}>File Trace</Button>
                        </div>

                        {/* Toolbar row */}
                        <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] text-gray-500">
                            <Button
                                size="sm"
                                variant={pathModeEnabled ? 'secondary' : 'ghost'}
                                className={`h-6 px-2.5 text-[10px] gap-1.5 ${pathModeEnabled ? 'bg-amber-500/10 border border-amber-500/30 text-amber-300 hover:bg-amber-500/15' : ''}`}
                                onClick={() => {
                                    const next = !pathModeEnabled;
                                    setPathModeEnabled(next);
                                    if (!next) clearPathState();
                                }}
                            >
                                <Crosshair className="h-3 w-3" />
                                {pathModeEnabled ? 'Pathfinder: ON' : 'Pathfinder'}
                            </Button>

                            {pathModeEnabled && (
                                <>
                                    <div className="h-3 w-px bg-white/[0.08]" />
                                    <Button size="sm" variant={pathComputeMode === 'shortest' ? 'secondary' : 'ghost'} className="h-6 px-2 text-[10px]" onClick={() => setPathComputeMode('shortest')}>Shortest</Button>
                                    <Button size="sm" variant={pathComputeMode === 'all' ? 'secondary' : 'ghost'} className="h-6 px-2 text-[10px]" onClick={() => setPathComputeMode('all')}>All paths</Button>
                                </>
                            )}

                            {pathStatus?.found && (
                                <span className="px-2 py-1 rounded border border-amber-500/30 bg-amber-500/10 text-amber-300">
                                    {pathStatus.mode === 'all'
                                        ? `${pathStatus.pathCount} path(s) found`
                                        : `Shortest path: ${pathStatus.hops} hop${pathStatus.hops !== 1 ? 's' : ''}`}
                                    {pathStatus.truncated ? ' (truncated)' : ''}
                                </span>
                            )}
                            {pathStatus && !pathStatus.found && (
                                <span className="px-2 py-1 rounded border border-gray-500/30 bg-gray-500/10 text-gray-400">No path found</span>
                            )}
                            {isPathLoading && (
                                <span className="px-2 py-1 rounded border border-white/[0.06] bg-white/[0.02] text-gray-400 animate-pulse">Resolving...</span>
                            )}
                        </div>

                        {/* Path mode: source/target assignment bar */}
                        <AnimatePresence>
                            {pathModeEnabled && (
                                <motion.div
                                    initial={{ opacity: 0, height: 0 }}
                                    animate={{ opacity: 1, height: 'auto' }}
                                    exit={{ opacity: 0, height: 0 }}
                                    className="overflow-hidden"
                                >
                                    <div className="mt-3 flex items-center gap-2 p-2.5 rounded-lg border border-white/[0.06] bg-white/[0.02]">
                                        {/* Source badge */}
                                        <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] min-w-0 ${sourceLabel ? 'border border-red-500/30 bg-red-500/10 text-red-300' : 'border border-dashed border-white/[0.1] text-gray-600'}`}>
                                            <span className="text-[9px] uppercase tracking-wider font-medium shrink-0 opacity-60">S</span>
                                            <span className="truncate">{sourceLabel || 'Click node...'}</span>
                                            {sourceLabel && (
                                                <button onClick={() => { pathSourceRef.current = null; setPathSource(null); pathOverlayRef.current = { nodeIds: new Set(), edgeKeys: new Set() }; setPathStatus(null); applyVisualOverlay(); }} className="ml-1 text-red-500/60 hover:text-red-400 shrink-0">&times;</button>
                                            )}
                                        </div>

                                        {/* Arrow / swap */}
                                        <button
                                            onClick={swapSourceTarget}
                                            disabled={!sourceLabel && !targetLabel}
                                            className="text-gray-600 hover:text-gray-400 disabled:opacity-30 transition-colors px-0.5"
                                            title="Swap source and target"
                                        >
                                            <CornerDownRight className="h-3.5 w-3.5" />
                                        </button>

                                        {/* Target badge */}
                                        <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] min-w-0 ${targetLabel ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border border-dashed border-white/[0.1] text-gray-600'}`}>
                                            <span className="text-[9px] uppercase tracking-wider font-medium shrink-0 opacity-60">T</span>
                                            <span className="truncate">{targetLabel || 'Click node...'}</span>
                                            {targetLabel && (
                                                <button onClick={() => { pathTargetRef.current = null; setPathTarget(null); pathOverlayRef.current = { nodeIds: new Set(), edgeKeys: new Set() }; setPathStatus(null); applyVisualOverlay(); }} className="ml-1 text-emerald-500/60 hover:text-emerald-400 shrink-0">&times;</button>
                                            )}
                                        </div>

                                        <div className="flex-1" />

                                        {pathAssignHint && (
                                            <span className="text-[10px] text-gray-600 italic">{pathAssignHint}</span>
                                        )}

                                        {(sourceLabel || targetLabel) && (
                                            <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px] text-gray-500" onClick={clearPathState}>Clear</Button>
                                        )}
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* File Trace: Search picker */}
                        <AnimatePresence mode="wait">
                            {activeGraph === 'file' && (
                                <motion.div
                                    key="file-trace-picker"
                                    initial={{ opacity: 0, marginTop: 0 }}
                                    animate={{ opacity: 1, marginTop: 12 }}
                                    exit={{ opacity: 0, marginTop: 0 }}
                                    transition={{ duration: 0.2 }}
                                    className="relative z-20"
                                >
                                    {sharedDocs.length === 0 ? (
                                        <div className="flex items-center gap-2 p-3 border border-white/[0.04] rounded-lg bg-white/[0.01]">
                                            <Share2 className="h-4 w-4 text-gray-600" />
                                            <p className="text-xs text-gray-500">No shared files to trace. Share a document first to see its trace.</p>
                                        </div>
                                    ) : (
                                        <div ref={fileSearchRef} className="relative">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-600" />
                                            <input
                                                type="text"
                                                placeholder={selectedDocName || "Search shared files to trace..."}
                                                value={fileSearchQuery}
                                                onChange={(e) => { setFileSearchQuery(e.target.value); setShowFilePicker(true); }}
                                                onFocus={() => setShowFilePicker(true)}
                                                className="w-full pl-9 pr-3 py-2 bg-white/[0.03] border border-white/[0.06] rounded-lg text-xs text-white placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-red-500/30 transition-all"
                                            />
                                            <AnimatePresence>
                                                {showFilePicker && (
                                                    <motion.div
                                                        initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                                                        className="absolute top-full mt-1 w-full bg-[#0a0a0a] border border-white/[0.08] rounded-lg shadow-2xl z-30 max-h-48 overflow-y-auto"
                                                    >
                                                        {filteredDocs.length === 0 ? (
                                                            <div className="px-4 py-3 text-xs text-gray-500">No matching shared files.</div>
                                                        ) : filteredDocs.map((doc) => (
                                                            <button
                                                                key={doc.id}
                                                                onClick={() => selectFileForTrace(doc)}
                                                                className={`w-full flex items-center gap-3 px-4 py-2.5 hover:bg-white/[0.04] transition-colors text-left border-b border-white/[0.04] last:border-b-0 cursor-pointer ${doc.id === selectedDoc ? 'bg-white/[0.04]' : ''}`}
                                                            >
                                                                <FileText className="h-3.5 w-3.5 text-gray-500 shrink-0" />
                                                                <div className="min-w-0 flex-1">
                                                                    <div className="text-xs text-gray-200 truncate">{doc.filename}</div>
                                                                </div>
                                                                <span className="text-[10px] text-gray-600 font-mono shrink-0 flex items-center gap-1">
                                                                    <Share2 className="h-2.5 w-2.5" />{doc.share_count}
                                                                </span>
                                                            </button>
                                                        ))}
                                                    </motion.div>
                                                )}
                                            </AnimatePresence>
                                        </div>
                                    )}
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </CardHeader>
                    <CardContent className="flex-1 p-0 relative min-h-[350px] bg-black isolate">
                        <div ref={graphRef} className="absolute inset-0 w-full h-full -z-10" />
                        {activeGraph === 'file' && !selectedDoc && (
                            <div className="absolute inset-0 bg-black/90 flex flex-col items-center justify-center z-10 transition-colors">
                                <Network className="h-8 w-8 text-gray-700 mb-2" />
                                <p className="text-xs text-gray-600">Select a shared file above to view its trace.</p>
                            </div>
                        )}
                    </CardContent>
                    <CardContent className="border-t border-white/[0.04] py-3 text-[10px] text-gray-500 flex items-center gap-4 flex-wrap">
                        <div className="flex items-center gap-1"><span className="h-2 w-2 bg-red-500 rounded-full" /> Root</div>
                        <div className="flex items-center gap-1"><span className="h-2 w-2 bg-white/40 rounded-full" /> Share</div>
                        <div className="flex items-center gap-1"><span className="h-2 w-2 bg-emerald-500 rounded-full" /> Online</div>
                        <div className="flex items-center gap-1"><span className="h-2 w-2 bg-gray-500 rounded-full" /> Offline</div>
                        <div className="flex items-center gap-1"><span className="h-2 w-2 bg-amber-400 rounded-full" /> Path</div>
                        {pathModeEnabled && (
                            <>
                                <div className="h-2 w-px bg-white/[0.08]" />
                                <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-full border border-red-500 bg-red-500/20" /> Source</div>
                                <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-full border border-emerald-500 bg-emerald-500/20" /> Target</div>
                            </>
                        )}
                    </CardContent>
                </Card>

                <div className="flex flex-col gap-4 shrink-0">

                    {/* Audit */}
                    <Card className="overflow-visible flex flex-col w-full">
                        <CardHeader className="pb-2 relative">
                            <CardTitle className="text-sm flex items-center gap-2 group cursor-help w-max">
                                <Shield className="h-3.5 w-3.5 text-white/60" /> Immutability Audit
                                <Info className="h-3 w-3 text-gray-500 group-hover:text-white transition-colors" />
                                <div className="absolute top-10 left-6 right-6 p-4 bg-black/80 backdrop-blur-xl border border-white/[0.12] text-xs leading-relaxed text-gray-300 rounded-xl opacity-0 invisible translate-y-2 group-hover:opacity-100 group-hover:visible group-hover:translate-y-0 transition-all duration-300 ease-out z-[60] shadow-[0_12px_40px_rgba(0,0,0,0.6)] ring-1 ring-white/[0.02] pointer-events-none">
                                    <div className="flex items-center gap-2 mb-1.5 text-white font-medium tracking-wide">
                                        <Shield className="h-3 w-3 text-emerald-400" /> Audit Mechanism
                                    </div>
                                    Verifies the cryptographic hash chain of the entire global event log (uploads, shares, deletes) to comprehensively detect tampering or revision.
                                </div>
                            </CardTitle>
                            <CardDescription>Verify the hash chain integrity.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Button onClick={handleVerify} isLoading={isVerifying} className="w-full md:w-auto px-8 mb-3" variant="secondary">Validate Chain</Button>
                            {auditResult && (
                                <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                                    className={`p-4 rounded-lg border flex items-start gap-3 backdrop-blur-xl transition-all duration-500 ${auditResult.valid ? 'border-emerald-500/30 bg-emerald-500/5 shadow-[0_0_15px_rgba(16,185,129,0.15)] ring-1 ring-emerald-500/10' : 'border-red-500/30 bg-red-500/5 shadow-[0_0_15px_rgba(255,7,58,0.15)] ring-1 ring-red-500/10'}`}>
                                    {auditResult.valid ? <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" /> : <XCircle className="h-5 w-5 text-red-500 shrink-0" />}
                                    <div>
                                        <h4 className={`text-sm font-semibold mb-0.5 ${auditResult.valid ? 'text-emerald-300' : 'text-red-400'}`}>{auditResult.valid ? 'Chain Integrity Verified' : 'Tampered Chain Detected'}</h4>
                                        <p className="text-xs text-gray-400">Validated continuous history of {auditResult.chain_length} cryptographic blocks.</p>
                                    </div>
                                </motion.div>
                            )}
                        </CardContent>
                    </Card>

                </div>
            </div>
        </div>
    );
}
