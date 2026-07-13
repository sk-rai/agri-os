"use client";

import { useEffect, useState } from "react";
import {
  inputCatalogApi,
  productCatalogApi,
  type AgriculturalProductDto,
  type CropStageInputRuleDto,
  type ManufacturerDto,
  type ProductCsvValidationResponse,
  type ProductCsvImportBatch,
} from "@/lib/api";
import { adminRoleLabel, hasAdminPermission, useAdminProfile } from "@/lib/admin-permissions";
import { getErrorMessage, isPermissionDenied, PermissionErrorCard } from "@/components/permission-error-card";

export default function ProductsPage() {
  const [manufacturers, setManufacturers] = useState<ManufacturerDto[]>([]);
  const [products, setProducts] = useState<AgriculturalProductDto[]>([]);
  const [rules, setRules] = useState<CropStageInputRuleDto[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvReport, setCsvReport] = useState<ProductCsvValidationResponse | null>(null);
  const [csvImports, setCsvImports] = useState<ProductCsvImportBatch[]>([]);
  const [csvBusy, setCsvBusy] = useState(false);
  const { profile: adminProfile, loading: loadingProfile } = useAdminProfile();
  const [mfg, setMfg] = useState({ code: "", canonical_name: "", short_name: "", country: "India", reason: "Created in admin" });
  const [product, setProduct] = useState({ code: "", canonical_input_code: "", manufacturer_code: "", brand_name: "", composition: "", registration_number: "", registration_authority: "", sku: "", quantity: "", unit: "kg", pack_label: "", barcode: "", reason: "Created in admin" });
  const [approval, setApproval] = useState({ project_id: "", product_code: "", enabled: true, preferred: false, display_order: "1000", reason: "Project product approval" });
  const [ruleFilter, setRuleFilter] = useState({ crop_code: "RICE", stage_code: "", activity_type: "", project_id: "" });
  const canEditCatalog = hasAdminPermission(adminProfile, "EDIT");
  const canEditProjectApprovals = hasAdminPermission(adminProfile, "PROJECT_EDIT");
  const [ruleDraft, setRuleDraft] = useState({ project_id: "", crop_code: "RICE", season_code: "KHARIF", stage_code: "TILLERING", activity_type: "FERTILIZER", input_code: "UREA_46_N", dosage_quantity: "45", dosage_unit: "kg", dosage_area_unit: "ACRE", min_quantity: "", max_quantity: "", priority: "1000", application_method: "", timing_note: "", safety_note: "", enabled: true, reason: "Stage dosage rule" });

  const load = async () => {
    try {
      const [m, p] = await Promise.all([productCatalogApi.manufacturers(), productCatalogApi.products({ includeInactive: true })]);
      setManufacturers(m.manufacturers);
      setProducts(p.products);
    } catch (e) { setError(e); }
  };
  const loadRules = async () => {
    try {
      const data = await inputCatalogApi.inputRules({ cropCode: ruleFilter.crop_code || undefined, stageCode: ruleFilter.stage_code || undefined, activityType: ruleFilter.activity_type || undefined, projectId: ruleFilter.project_id || undefined, includeDisabled: true });
      setRules(data.rules);
    } catch (e) { setError(e); }
  };
  const loadProductImportHistory = async () => {
    try {
      const data = await productCatalogApi.importHistory({ limit: 5 });
      setCsvImports(data.imports);
    } catch (e) { setError(e); }
  };
  useEffect(() => {
    void load();
    void loadRules();
    void loadProductImportHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const createMfg = async () => { if (!canEditCatalog) { setError("Your current role can view products but cannot edit the product catalog."); return; } setBusy(true); setError(null); try { await productCatalogApi.createManufacturer({ ...mfg, aliases: [] }); setMfg({ ...mfg, code: "", canonical_name: "", short_name: "" }); setNotice("Manufacturer created"); await load(); } catch (e) { setError(e); } finally { setBusy(false); } };
  const createProduct = async () => { if (!canEditCatalog) { setError("Your current role can view products but cannot edit the product catalog."); return; } setBusy(true); setError(null); try { await productCatalogApi.createProduct({ code: product.code, canonical_input_code: product.canonical_input_code, manufacturer_code: product.manufacturer_code, brand_name: product.brand_name, composition: product.composition || null, registration_number: product.registration_number || null, registration_authority: product.registration_authority || null, country: "India", packages: [{ sku: product.sku, quantity: product.quantity, unit: product.unit, pack_label: product.pack_label, barcode: product.barcode || null }], reason: product.reason }); setNotice("Product and package created"); await load(); } catch (e) { setError(e); } finally { setBusy(false); } };
  const approve = async () => { if (!canEditProjectApprovals) { setError("Your current role can view products but cannot change project product approvals."); return; } setBusy(true); setError(null); try { await productCatalogApi.approveProduct(approval.project_id, approval.product_code, { enabled: approval.enabled, preferred: approval.preferred, display_order: Number(approval.display_order), reason: approval.reason }); setNotice("Project approval saved"); } catch (e) { setError(e); } finally { setBusy(false); } };
  const createRule = async () => { if (!canEditCatalog) { setError("Your current role can view dosage rules but cannot edit input rules."); return; } setBusy(true); setError(null); try { await inputCatalogApi.createInputRule({ project_id: ruleDraft.project_id || null, crop_code: ruleDraft.crop_code, season_code: ruleDraft.season_code || null, stage_code: ruleDraft.stage_code, activity_type: ruleDraft.activity_type, input_code: ruleDraft.input_code, enabled: ruleDraft.enabled, priority: Number(ruleDraft.priority || 1000), dosage_quantity: ruleDraft.dosage_quantity || null, dosage_unit: ruleDraft.dosage_unit || null, dosage_area_unit: ruleDraft.dosage_area_unit || "ACRE", min_quantity: ruleDraft.min_quantity || null, max_quantity: ruleDraft.max_quantity || null, application_method: ruleDraft.application_method || null, timing_note: ruleDraft.timing_note || null, safety_note: ruleDraft.safety_note || null, allowed_product_codes: [], metadata: {}, reason: ruleDraft.reason }); setNotice("Input dosage rule saved"); await loadRules(); } catch (e) { setError(e); } finally { setBusy(false); } };
  const toggleRule = async (rule: CropStageInputRuleDto) => { if (!canEditCatalog) { setError("Your current role can view dosage rules but cannot edit input rules."); return; } setBusy(true); setError(null); try { await inputCatalogApi.updateInputRule(rule.id, { enabled: !rule.enabled, reason: rule.enabled ? "Disabled from admin" : "Enabled from admin" }); await loadRules(); } catch (e) { setError(e); } finally { setBusy(false); } };
  const downloadProductTemplate = () => { setError(null); productCatalogApi.downloadCsvTemplate().catch(setError); };
  const exportProducts = (includeInactive = false) => { setError(null); productCatalogApi.exportCsv(includeInactive).catch(setError); };
  const validateProductCsv = async () => {
    if (!csvFile) { setError("Choose a product catalog CSV file first."); return; }
    setCsvBusy(true); setError(null); setCsvReport(null);
    try { const batch = await productCatalogApi.validateCsv(csvFile); setCsvReport(batch.report); await loadProductImportHistory(); }
    catch (e) { setError(e); }
    finally { setCsvBusy(false); }
  };
  const applyProductCsvImport = async (batch: ProductCsvImportBatch, reason: string) => {
    if (!canEditCatalog) { setError("Your current role can view product CSV imports but cannot apply them."); return; }
    setCsvBusy(true); setError(null);
    try { const applied = await productCatalogApi.applyCsv(batch.batch_id, reason); setCsvReport(applied.report); setNotice("Product CSV import applied"); await Promise.all([load(), loadProductImportHistory()]); }
    catch (e) { setError(e); }
    finally { setCsvBusy(false); }
  };

  return <div>
    <h1 className="text-2xl font-bold">Products, Manufacturers & Dosage Rules</h1>
    <p className="mt-1 text-sm text-gray-500">Map branded products to canonical inputs, approve products per project, and define crop-stage dosage guidance.</p>
    {isPermissionDenied(error) ? <PermissionErrorCard error={error} className="mt-4" /> : error ? <p className="mt-4 rounded bg-red-50 p-3 text-sm text-red-700">{getErrorMessage(error)}</p> : null}{notice && <p className="mt-4 rounded bg-green-50 p-3 text-sm text-green-700">{notice}</p>}
    {!loadingProfile && (!canEditCatalog || !canEditProjectApprovals) && <div className="mt-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><p className="font-semibold">Product catalog permissions</p><p className="mt-1">Role {adminRoleLabel(adminProfile)}: catalog edits {canEditCatalog ? "allowed" : "read-only"}; project approvals {canEditProjectApprovals ? "allowed" : "read-only"}. Browsing remains available.</p></div>}
    <section className="mt-6 rounded border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="font-semibold">Product catalog CSV foundation</p>
          <p className="mt-1 text-blue-800">Download the template or export the current manufacturer, branded product, and package catalog. Validate, review, and apply product catalog changes through the persisted import lifecycle.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={downloadProductTemplate} className="rounded border border-blue-200 bg-white px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50">Download template</button>
          <button onClick={() => exportProducts(false)} className="rounded border border-blue-200 bg-white px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50">Export active</button>
          <button onClick={() => exportProducts(true)} className="rounded border border-blue-200 bg-white px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50">Export all</button>
        </div>
      </div>
      <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
        <input type="file" accept=".csv,text/csv" onChange={(event) => { setCsvFile(event.target.files?.[0] || null); setCsvReport(null); }} className="text-xs" />
        <button onClick={validateProductCsv} disabled={csvBusy || !csvFile || !canEditCatalog} title={canEditCatalog ? undefined : "Your role cannot validate product CSV imports."} className="rounded bg-blue-700 px-3 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:bg-gray-300">{csvBusy ? "Validating..." : "Validate CSV"}</button>
        {csvFile ? <span className="text-xs text-blue-800">Selected: {csvFile.name}</span> : null}
      </div>
      {csvReport ? <ProductCsvValidationPanel report={csvReport} /> : null}
      <ProductCsvImportHistoryPanel imports={csvImports} canEdit={canEditCatalog} busy={csvBusy} onRefresh={loadProductImportHistory} onApply={applyProductCsvImport} />
    </section>
    <div className="mt-6 grid gap-5 xl:grid-cols-3">
      <Panel title="New manufacturer"><Field label="Code" value={mfg.code} set={v => setMfg({ ...mfg, code: v })} /><Field label="Name" value={mfg.canonical_name} set={v => setMfg({ ...mfg, canonical_name: v })} /><Field label="Short name" value={mfg.short_name} set={v => setMfg({ ...mfg, short_name: v })} /><button disabled={busy || !canEditCatalog || !mfg.code || !mfg.canonical_name} title={canEditCatalog ? undefined : "Your role cannot edit the product catalog."} onClick={createMfg} className="mt-3 rounded bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50">Create manufacturer</button></Panel>
      <Panel title="New branded product"><Field label="Product code" value={product.code} set={v => setProduct({ ...product, code: v })} /><Field label="Canonical input code" value={product.canonical_input_code} set={v => setProduct({ ...product, canonical_input_code: v })} /><label className="text-xs text-gray-500">Manufacturer<select value={product.manufacturer_code} onChange={e => setProduct({ ...product, manufacturer_code: e.target.value })} className="mt-1 w-full rounded border p-2 text-sm"><option value="">Select</option>{manufacturers.map(x => <option key={x.code}>{x.code}</option>)}</select></label><Field label="Brand name" value={product.brand_name} set={v => setProduct({ ...product, brand_name: v })} /><Field label="Composition" value={product.composition} set={v => setProduct({ ...product, composition: v })} /><Field label="Registration number" value={product.registration_number} set={v => setProduct({ ...product, registration_number: v })} /><div className="grid grid-cols-2 gap-2"><Field label="SKU" value={product.sku} set={v => setProduct({ ...product, sku: v })} /><Field label="Pack label" value={product.pack_label} set={v => setProduct({ ...product, pack_label: v })} /><Field label="Quantity" value={product.quantity} set={v => setProduct({ ...product, quantity: v })} /><Field label="Unit" value={product.unit} set={v => setProduct({ ...product, unit: v })} /></div><button disabled={busy || !canEditCatalog || !product.code || !product.manufacturer_code || !product.sku} title={canEditCatalog ? undefined : "Your role cannot edit the product catalog."} onClick={createProduct} className="mt-3 rounded bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50">Create product</button></Panel>
      <Panel title="Project approval"><Field label="Project ID" value={approval.project_id} set={v => setApproval({ ...approval, project_id: v })} /><label className="text-xs text-gray-500">Product<select value={approval.product_code} onChange={e => setApproval({ ...approval, product_code: e.target.value })} className="mt-1 w-full rounded border p-2 text-sm"><option value="">Select</option>{products.filter(x => x.status === "ACTIVE").map(x => <option key={x.code}>{x.code}</option>)}</select></label><label className="flex gap-2 text-sm"><input type="checkbox" checked={approval.enabled} onChange={e => setApproval({ ...approval, enabled: e.target.checked })} />Enabled</label><label className="flex gap-2 text-sm"><input type="checkbox" checked={approval.preferred} onChange={e => setApproval({ ...approval, preferred: e.target.checked })} />Preferred</label><Field label="Display order" value={approval.display_order} set={v => setApproval({ ...approval, display_order: v })} /><Field label="Reason" value={approval.reason} set={v => setApproval({ ...approval, reason: v })} /><button disabled={busy || !canEditProjectApprovals || !approval.project_id || !approval.product_code} title={canEditProjectApprovals ? undefined : "Your role cannot change project product approvals."} onClick={approve} className="mt-3 rounded bg-green-700 px-4 py-2 text-sm text-white disabled:opacity-50">Save approval</button></Panel>
    </div>
    <Panel title="Crop-stage input compatibility & dosage"><div className="grid gap-3 md:grid-cols-4"><Field label="Crop" value={ruleDraft.crop_code} set={v => setRuleDraft({ ...ruleDraft, crop_code: v })} /><Field label="Season" value={ruleDraft.season_code} set={v => setRuleDraft({ ...ruleDraft, season_code: v })} /><Field label="Stage" value={ruleDraft.stage_code} set={v => setRuleDraft({ ...ruleDraft, stage_code: v })} /><Field label="Activity" value={ruleDraft.activity_type} set={v => setRuleDraft({ ...ruleDraft, activity_type: v })} /><Field label="Input code" value={ruleDraft.input_code} set={v => setRuleDraft({ ...ruleDraft, input_code: v })} /><Field label="Quantity" value={ruleDraft.dosage_quantity} set={v => setRuleDraft({ ...ruleDraft, dosage_quantity: v })} /><Field label="Unit" value={ruleDraft.dosage_unit} set={v => setRuleDraft({ ...ruleDraft, dosage_unit: v })} /><Field label="Per area" value={ruleDraft.dosage_area_unit} set={v => setRuleDraft({ ...ruleDraft, dosage_area_unit: v })} /><Field label="Min qty" value={ruleDraft.min_quantity} set={v => setRuleDraft({ ...ruleDraft, min_quantity: v })} /><Field label="Max qty" value={ruleDraft.max_quantity} set={v => setRuleDraft({ ...ruleDraft, max_quantity: v })} /><Field label="Project ID (optional)" value={ruleDraft.project_id} set={v => setRuleDraft({ ...ruleDraft, project_id: v })} /><Field label="Reason" value={ruleDraft.reason} set={v => setRuleDraft({ ...ruleDraft, reason: v })} /></div><div className="mt-3 grid gap-3 md:grid-cols-3"><Field label="Application method" value={ruleDraft.application_method} set={v => setRuleDraft({ ...ruleDraft, application_method: v })} /><Field label="Timing note" value={ruleDraft.timing_note} set={v => setRuleDraft({ ...ruleDraft, timing_note: v })} /><Field label="Safety note" value={ruleDraft.safety_note} set={v => setRuleDraft({ ...ruleDraft, safety_note: v })} /></div><button disabled={busy || !canEditCatalog || !ruleDraft.crop_code || !ruleDraft.stage_code || !ruleDraft.input_code} title={canEditCatalog ? undefined : "Your role cannot edit input dosage rules."} onClick={createRule} className="mt-3 rounded bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50">Create dosage rule</button></Panel>
    <div className="mt-6 grid gap-6 xl:grid-cols-2"><DataTable title="Branded products" headers={["Code", "Brand", "Canonical input", "Manufacturer", "Packages", "Status"]}>{products.map(x => <tr key={x.code}><td className="p-3 font-mono text-xs">{x.code}</td><td className="p-3 font-medium">{x.brand_name}</td><td className="p-3">{x.canonical_input_code}</td><td className="p-3">{x.manufacturer_name}</td><td className="p-3">{x.packages.map(p => p.pack_label).join(", ")}</td><td className="p-3"><button disabled={!canEditCatalog} title={canEditCatalog ? undefined : "Your role cannot edit the product catalog."} onClick={async () => { if (!canEditCatalog) return; await productCatalogApi.updateProduct(x.code, { status: x.status === "ACTIVE" ? "DISCONTINUED" : "ACTIVE", reason: "Admin status change" }); await load(); }} className="rounded border px-2 py-1 text-xs disabled:opacity-50">{x.status}</button></td></tr>)}</DataTable><div><div className="mb-3 grid grid-cols-4 gap-2"><Field label="Rule crop" value={ruleFilter.crop_code} set={v => setRuleFilter({ ...ruleFilter, crop_code: v })} /><Field label="Rule stage" value={ruleFilter.stage_code} set={v => setRuleFilter({ ...ruleFilter, stage_code: v })} /><Field label="Rule activity" value={ruleFilter.activity_type} set={v => setRuleFilter({ ...ruleFilter, activity_type: v })} /><button onClick={loadRules} className="mt-5 rounded border px-3 py-2 text-sm">Refresh</button></div><DataTable title="Dosage rules" headers={["Scope", "Crop/stage", "Input", "Dosage", "Enabled"]}>{rules.map(r => <tr key={r.id}><td className="p-3">{r.rule_scope}</td><td className="p-3"><div>{r.crop_code} · {r.stage_code}</div><div className="text-xs text-gray-500">{r.activity_type}</div></td><td className="p-3"><div className="font-medium">{r.input_name}</div><div className="font-mono text-xs">{r.input_code}</div></td><td className="p-3">{r.dosage.quantity || "-"} {r.dosage.unit || ""}/{r.dosage.area_unit}</td><td className="p-3"><button disabled={!canEditCatalog} title={canEditCatalog ? undefined : "Your role cannot edit input dosage rules."} onClick={() => toggleRule(r)} className="rounded border px-2 py-1 text-xs disabled:opacity-50">{r.enabled ? "Enabled" : "Disabled"}</button></td></tr>)}</DataTable></div></div>
  </div>;
}
function ProductCsvImportHistoryPanel({ imports, canEdit, busy, onRefresh, onApply }: { imports: ProductCsvImportBatch[]; canEdit: boolean; busy: boolean; onRefresh: () => void; onApply: (batch: ProductCsvImportBatch, reason: string) => void }) {
  const [reason, setReason] = useState("Apply validated product catalog import");
  return <div className="mt-4 rounded border border-blue-100 bg-white p-4 text-sm text-gray-900">
    <div className="flex items-center justify-between gap-3">
      <div>
        <p className="font-semibold">Recent product CSV validations</p>
        <p className="mt-1 text-xs text-gray-500">Validated and invalid batches are retained briefly so admins can review and apply operator uploads safely.</p>
      </div>
      <button onClick={onRefresh} className="rounded border px-3 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50">Refresh</button>
    </div>
    <input value={reason} onChange={(event) => setReason(event.target.value)} className="mt-3 w-full rounded border px-3 py-2 text-xs text-gray-900" placeholder="Reason for applying product import" />
    {imports.length ? <div className="mt-3 overflow-x-auto">
      <table className="min-w-full text-left text-xs">
        <thead className="text-gray-500"><tr><th className="px-2 py-2">Created</th><th className="px-2 py-2">File</th><th className="px-2 py-2">Status</th><th className="px-2 py-2">Rows</th><th className="px-2 py-2">Issues</th><th className="px-2 py-2">Expires</th><th className="px-2 py-2">Action</th></tr></thead>
        <tbody>
          {imports.map((item) => <tr key={item.batch_id} className="border-t">
            <td className="px-2 py-2">{new Date(item.created_at).toLocaleString()}</td>
            <td className="px-2 py-2">{item.file_name || "-"}</td>
            <td className="px-2 py-2"><span className={`rounded px-2 py-1 font-semibold ${item.status === "VALIDATED" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>{item.status}</span></td>
            <td className="px-2 py-2">{item.report.summary.total}</td>
            <td className="px-2 py-2">{item.report.summary.errors} errors · {item.report.summary.warnings} warnings</td>
            <td className="px-2 py-2">{new Date(item.expires_at).toLocaleString()}</td>
            <td className="px-2 py-2">{item.can_apply ? <button disabled={busy || !canEdit || reason.trim().length < 3} title={canEdit ? undefined : "Your role cannot apply product imports."} onClick={() => onApply(item, reason.trim())} className="rounded bg-green-700 px-2 py-1 text-xs font-semibold text-white disabled:opacity-50">Apply</button> : <span className="text-gray-400">-</span>}</td>
          </tr>)}
        </tbody>
      </table>
    </div> : <p className="mt-3 rounded bg-gray-50 p-3 text-xs text-gray-500">No product CSV validation batches yet.</p>}
  </div>;
}
function ProductCsvValidationPanel({ report }: { report: ProductCsvValidationResponse }) {
  const rowsWithIssues = report.rows.filter((row) => row.errors.length || row.warnings.length);
  const previewRows = rowsWithIssues.length ? rowsWithIssues.slice(0, 8) : report.rows.slice(0, 8);
  return <div className="mt-4 rounded border border-blue-100 bg-white p-4 text-sm text-gray-900">
    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
      <div>
        <p className="font-semibold">Validation result: {report.can_apply ? "Ready to apply" : "Needs fixes"}</p>
        <p className="mt-1 text-xs text-gray-500">{report.message}</p>
      </div>
      <span className="rounded bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">{report.mode}</span>
    </div>
    <div className="mt-3 grid gap-2 md:grid-cols-6">
      <MiniStat label="Rows" value={report.summary.total} />
      <MiniStat label="Create" value={report.summary.create} />
      <MiniStat label="Update" value={report.summary.update} />
      <MiniStat label="Invalid" value={report.summary.invalid} />
      <MiniStat label="Warnings" value={report.summary.warnings} />
      <MiniStat label="Errors" value={report.summary.errors} />
    </div>
    <div className="mt-4 overflow-x-auto">
      <table className="min-w-full text-left text-xs">
        <thead className="text-gray-500"><tr><th className="px-2 py-2">Row</th><th className="px-2 py-2">Product</th><th className="px-2 py-2">SKU</th><th className="px-2 py-2">Action</th><th className="px-2 py-2">Diagnostics</th></tr></thead>
        <tbody>
          {previewRows.map((row) => <tr key={`${row.row_number}-${row.package_sku}`} className="border-t">
            <td className="px-2 py-2">{row.row_number}</td><td className="px-2 py-2 font-mono">{row.product_code || "-"}</td><td className="px-2 py-2 font-mono">{row.package_sku || "-"}</td><td className="px-2 py-2">{row.action}</td>
            <td className="px-2 py-2">{[...row.errors, ...row.warnings].length ? [...row.errors, ...row.warnings].map((issue, index) => <p key={`${issue.code}-${index}`}><span className="font-semibold">{issue.field}/{issue.code}:</span> {issue.message}</p>) : <span className="text-gray-400">No issues</span>}</td>
          </tr>)}
        </tbody>
      </table>
    </div>
  </div>;
}
function MiniStat({ label, value }: { label: string; value: string | number }) { return <div className="rounded bg-gray-50 p-2"><p className="text-[10px] uppercase text-gray-400">{label}</p><p className="text-lg font-bold text-gray-900">{value}</p></div>; }
function Panel({ title, children }: { title: string; children: React.ReactNode }) { return <div className="mt-6 space-y-3 rounded bg-white p-5 shadow"><h2 className="font-semibold">{title}</h2>{children}</div>; }
function Field({ label, value, set }: { label: string; value: string; set: (v: string) => void }) { return <label className="block text-xs text-gray-500">{label}<input value={value} onChange={e => set(e.target.value)} className="mt-1 w-full rounded border p-2 text-sm text-gray-900" /></label>; }
function DataTable({ title, headers, children }: { title: string; headers: string[]; children: React.ReactNode }) { return <div className="overflow-hidden rounded bg-white shadow"><h2 className="border-b p-3 font-semibold">{title}</h2><table className="w-full text-sm"><thead className="bg-gray-50"><tr>{headers.map(x => <th key={x} className="p-3 text-left">{x}</th>)}</tr></thead><tbody className="divide-y">{children}</tbody></table></div>; }