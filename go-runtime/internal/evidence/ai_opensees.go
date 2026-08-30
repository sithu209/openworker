package evidence

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

const (
	AIOpenSeesCapabilityID  = "structural.ai_opensees.authority.analyze"
	AIOpenSeesRepository    = "liuxb99/AI-OpenSees"
	AIOpenSeesHost          = "O87"
	AIOpenSeesResultSchema  = "ai-opensees/analysis-result/v0.6"
	AIOpenSeesReceiptSchema = "ai-opensees/operator-evidence/v0.9"
	AIOpenSeesRuntimeSchema = "ai-opensees/mct-authority-runtime-state/v0.5"
)

type AIOpenSeesArtifact struct {
	Name string `json:"name"`
	Path string `json:"path"`
	Bytes int64 `json:"bytes"`
	SHA256 string `json:"sha256"`
}

type AIOpenSeesOperatorEvidence struct {
	SchemaVersion string `json:"schema_version"`
	CapabilityID string `json:"capability_id"`
	Repository string `json:"repository"`
	CommitSHA string `json:"commit_sha"`
	RunID string `json:"run_id"`
	RunAttempt string `json:"run_attempt"`
	AssignedHostname string `json:"assigned_hostname"`
	MCTPath string `json:"mct_path"`
	MCTSHA256 string `json:"mct_sha256"`
	RuntimeConfig string `json:"runtime_config"`
	RuntimeConfigSHA256 string `json:"runtime_config_sha256"`
	AuthorityGeneration int64 `json:"authority_generation"`
	AuthorityCatalogRoot string `json:"authority_catalog_root"`
	AuthorityEntryCount int `json:"authority_entry_count"`
	ElasticMaterialAuthorityCount int `json:"elastic_material_authority_count"`
	PrismaticSectionAuthorityCount int `json:"prismatic_section_authority_count"`
	StaticNodalLoadAuthorityCount int `json:"static_nodal_load_authority_count"`
	ActiveSourceSHA256 string `json:"active_source_sha256"`
	ActiveSourceAuthorityCount int `json:"active_source_authority_count"`
	ActiveSourceElasticMaterialAuthorityCount int `json:"active_source_elastic_material_authority_count"`
	ActiveSourcePrismaticSectionAuthorityCount int `json:"active_source_prismatic_section_authority_count"`
	ActiveSourceStaticNodalLoadAuthorityCount int `json:"active_source_static_nodal_load_authority_count"`
	ActiveSourceCoverageValid bool `json:"active_source_coverage_valid"`
	ActiveSourceCivilVersion string `json:"active_source_civil_version"`
	ActiveSourceCivilBuild string `json:"active_source_civil_build"`
	ActiveSourceExportedAt string `json:"active_source_exported_at"`
	ActiveSourceExportMethod string `json:"active_source_export_method"`
	ActiveSourceExportProvenanceValid bool `json:"active_source_export_provenance_valid"`
	ActiveSourceCohortValid bool `json:"active_source_cohort_valid"`
	AuthoritySnapshotSHA256 string `json:"authority_snapshot_sha256"`
	OpenSeesExecutable string `json:"opensees_executable"`
	OpenSeesExecutableSHA256 string `json:"opensees_executable_sha256"`
	Solver string `json:"solver"`
	SolverVersion string `json:"solver_version"`
	SolverRawExitCode int `json:"solver_raw_exit_code"`
	Workspace string `json:"workspace"`
	Status string `json:"status"`
	Artifacts []AIOpenSeesArtifact `json:"artifacts"`
}

type AIOpenSeesAnalysisResult struct {
	SchemaVersion string `json:"schema_version"`
	Status string `json:"status"`
	Solver string `json:"solver"`
	SolverExecutable string `json:"solver_executable"`
	SolverVersion string `json:"solver_version"`
	RawExitCode int `json:"raw_exit_code"`
	SourcePath string `json:"source_path"`
	SourceSHA256 string `json:"source_sha256"`
	AuthorityRuntimeUsed bool `json:"authority_runtime_used"`
	AuthorityGeneration int64 `json:"authority_generation"`
	AuthorityConfigPath string `json:"authority_config_path"`
	AuthorityCatalogRoot string `json:"authority_catalog_root"`
	AuthorityEntryCount int `json:"authority_entry_count"`
	AuthoritySnapshotSHA256 string `json:"authority_snapshot_sha256"`
	ScriptPath string `json:"script_path"`
	ScriptSHA256 string `json:"script_sha256"`
	StdoutPath string `json:"stdout_path"`
	StdoutSHA256 string `json:"stdout_sha256"`
	StderrPath string `json:"stderr_path"`
	StderrSHA256 string `json:"stderr_sha256"`
	GeometryJSONPath string `json:"geometry_json_path"`
	GeometryJSONSHA256 string `json:"geometry_json_sha256"`
	DeformedOBJPath string `json:"deformed_obj_path"`
	DeformedOBJSHA256 string `json:"deformed_obj_sha256"`
	DeformationSVGPath string `json:"deformation_svg_path"`
	DeformationSVGSHA256 string `json:"deformation_svg_sha256"`
	DisplacementCSVPath string `json:"displacement_csv_path"`
	DisplacementCSVSHA256 string `json:"displacement_csv_sha256"`
	ReactionCSVPath string `json:"reaction_csv_path"`
	ReactionCSVSHA256 string `json:"reaction_csv_sha256"`
}

type AIOpenSeesRuntimeState struct {
	SchemaVersion string `json:"schema_version"`
	Ready bool `json:"ready"`
	Generation int64 `json:"generation"`
	ConfigPath string `json:"config_path"`
	CatalogRoot string `json:"catalog_root"`
	EntryCount int `json:"entry_count"`
	ElasticMaterialAuthorityCount int `json:"elastic_material_authority_count"`
	PrismaticSectionAuthorityCount int `json:"prismatic_section_authority_count"`
	StaticNodalLoadAuthorityCount int `json:"static_nodal_load_authority_count"`
	ActiveSourceSHA256 string `json:"active_source_sha256"`
	ActiveSourceAuthorityCount int `json:"active_source_authority_count"`
	ActiveSourceElasticMaterialAuthorityCount int `json:"active_source_elastic_material_authority_count"`
	ActiveSourcePrismaticSectionAuthorityCount int `json:"active_source_prismatic_section_authority_count"`
	ActiveSourceStaticNodalLoadAuthorityCount int `json:"active_source_static_nodal_load_authority_count"`
	ActiveSourceCoverageValid bool `json:"active_source_coverage_valid"`
	ActiveSourceCivilVersion string `json:"active_source_civil_version"`
	ActiveSourceCivilBuild string `json:"active_source_civil_build"`
	ActiveSourceExportedAt string `json:"active_source_exported_at"`
	ActiveSourceExportMethod string `json:"active_source_export_method"`
	ActiveSourceExportProvenanceValid bool `json:"active_source_export_provenance_valid"`
	ActiveSourceCohortValid bool `json:"active_source_cohort_valid"`
	SnapshotSHA256 string `json:"snapshot_sha256"`
	SnapshotValid bool `json:"snapshot_valid"`
}

type AIOpenSeesEvidenceReport struct {
	SchemaVersion string `json:"schema_version"`
	Accepted bool `json:"accepted"`
	Workspace string `json:"workspace"`
	AssignedHostname string `json:"assigned_hostname,omitempty"`
	RunID string `json:"run_id,omitempty"`
	AuthorityGeneration int64 `json:"authority_generation,omitempty"`
	AuthoritySnapshotSHA256 string `json:"authority_snapshot_sha256,omitempty"`
	VerifiedArtifacts int `json:"verified_artifacts"`
	Blockers []string `json:"blockers"`
}

func sha256File(path string) (string, int64, error) {
	f, err := os.Open(path); if err != nil { return "", 0, err }; defer f.Close()
	stat, err := f.Stat(); if err != nil { return "", 0, err }
	h := sha256.New(); if _, err := io.Copy(h, f); err != nil { return "", 0, err }
	return hex.EncodeToString(h.Sum(nil)), stat.Size(), nil
}
func readJSON(path string, target any) error { data,err:=os.ReadFile(path); if err!=nil{return err}; if len(data)==0{return fmt.Errorf("empty JSON file")}; return json.Unmarshal(data,target) }
func isSHA256(value string) bool { if len(value)!=64{return false}; _,err:=hex.DecodeString(value); return err==nil }
func isGitCommitSHA(value string) bool { if len(value)!=40&&len(value)!=64{return false}; _,err:=hex.DecodeString(value); return err==nil }
func isPositiveDecimal(value string) bool { if strings.TrimSpace(value)==""{return false}; n,err:=strconv.ParseUint(value,10,64); return err==nil&&n>0 }
func samePath(a,b string) bool { if strings.TrimSpace(a)==""||strings.TrimSpace(b)==""{return false}; ca,ea:=filepath.Abs(filepath.Clean(a)); cb,eb:=filepath.Abs(filepath.Clean(b)); if ea!=nil||eb!=nil{return false}; return strings.EqualFold(ca,cb) }

func ValidateAIOpenSeesWorkspace(workspace string) AIOpenSeesEvidenceReport {
	report:=AIOpenSeesEvidenceReport{SchemaVersion:"openworker/ai-opensees-evidence-report/v0.9",Workspace:filepath.Clean(workspace),Blockers:[]string{}}
	add:=func(code string){report.Blockers=append(report.Blockers,code)}
	if strings.TrimSpace(workspace)==""{add("WORKSPACE_EMPTY");return report}
	var receipt AIOpenSeesOperatorEvidence; if err:=readJSON(filepath.Join(workspace,"operator-evidence.json"),&receipt);err!=nil{add("OPERATOR_EVIDENCE_INVALID:"+err.Error());return report}
	var result AIOpenSeesAnalysisResult; if err:=readJSON(filepath.Join(workspace,"analysis-result.json"),&result);err!=nil{add("ANALYSIS_RESULT_INVALID:"+err.Error());return report}
	var runtime AIOpenSeesRuntimeState; if err:=readJSON(filepath.Join(workspace,"authority-runtime-state.json"),&runtime);err!=nil{add("AUTHORITY_RUNTIME_STATE_INVALID:"+err.Error());return report}
	report.AssignedHostname=receipt.AssignedHostname; report.RunID=receipt.RunID; report.AuthorityGeneration=receipt.AuthorityGeneration; report.AuthoritySnapshotSHA256=receipt.AuthoritySnapshotSHA256

	if receipt.SchemaVersion!=AIOpenSeesReceiptSchema{add("OPERATOR_EVIDENCE_SCHEMA_MISMATCH")}
	if receipt.CapabilityID!=AIOpenSeesCapabilityID{add("CAPABILITY_ID_MISMATCH")}
	if receipt.Repository!=AIOpenSeesRepository{add("REPOSITORY_MISMATCH")}
	if !isGitCommitSHA(receipt.CommitSHA){add("COMMIT_SHA_INVALID")}
	if !isPositiveDecimal(receipt.RunID){add("RUN_ID_INVALID")}
	if !isPositiveDecimal(receipt.RunAttempt){add("RUN_ATTEMPT_INVALID")}
	if !strings.EqualFold(receipt.AssignedHostname,AIOpenSeesHost){add("ASSIGNED_HOST_MISMATCH")}
	if receipt.Status!="complete"{add("OPERATOR_STATUS_NOT_COMPLETE")}
	if receipt.AuthorityGeneration<1{add("AUTHORITY_GENERATION_INVALID")}
	if receipt.AuthorityEntryCount<1{add("AUTHORITY_ENTRY_COUNT_INVALID")}
	if receipt.ElasticMaterialAuthorityCount<1{add("MATERIAL_AUTHORITY_COVERAGE_MISSING")}
	if receipt.PrismaticSectionAuthorityCount<1{add("SECTION_AUTHORITY_COVERAGE_MISSING")}
	if receipt.StaticNodalLoadAuthorityCount<1{add("STATIC_NODAL_LOAD_AUTHORITY_COVERAGE_MISSING")}
	if receipt.ElasticMaterialAuthorityCount+receipt.PrismaticSectionAuthorityCount+receipt.StaticNodalLoadAuthorityCount!=receipt.AuthorityEntryCount{add("AUTHORITY_COVERAGE_COUNT_MISMATCH")}
	if !receipt.ActiveSourceCoverageValid{add("ACTIVE_SOURCE_AUTHORITY_COVERAGE_INVALID")}
	if !receipt.ActiveSourceCohortValid{add("ACTIVE_SOURCE_CIVIL_COHORT_INVALID")}
	if !receipt.ActiveSourceExportProvenanceValid{add("ACTIVE_SOURCE_GUI_EXPORT_PROVENANCE_INVALID")}
	if strings.TrimSpace(receipt.ActiveSourceCivilVersion)==""{add("ACTIVE_SOURCE_CIVIL_VERSION_EMPTY")}
	if strings.TrimSpace(receipt.ActiveSourceCivilBuild)==""{add("ACTIVE_SOURCE_CIVIL_BUILD_EMPTY")}
	if strings.TrimSpace(receipt.ActiveSourceExportedAt)==""{add("ACTIVE_SOURCE_EXPORTED_AT_EMPTY")}
	if strings.TrimSpace(receipt.ActiveSourceExportMethod)==""{add("ACTIVE_SOURCE_EXPORT_METHOD_EMPTY")}
	if !isSHA256(receipt.ActiveSourceSHA256){add("ACTIVE_SOURCE_SHA256_INVALID")}
	if !strings.EqualFold(receipt.ActiveSourceSHA256,receipt.MCTSHA256){add("ACTIVE_SOURCE_MCT_SHA256_MISMATCH")}
	if receipt.ActiveSourceAuthorityCount<1{add("ACTIVE_SOURCE_AUTHORITY_COUNT_INVALID")}
	if receipt.ActiveSourceElasticMaterialAuthorityCount<1{add("ACTIVE_SOURCE_MATERIAL_AUTHORITY_COVERAGE_MISSING")}
	if receipt.ActiveSourcePrismaticSectionAuthorityCount<1{add("ACTIVE_SOURCE_SECTION_AUTHORITY_COVERAGE_MISSING")}
	if receipt.ActiveSourceStaticNodalLoadAuthorityCount<1{add("ACTIVE_SOURCE_STATIC_NODAL_LOAD_AUTHORITY_COVERAGE_MISSING")}
	if receipt.ActiveSourceElasticMaterialAuthorityCount+receipt.ActiveSourcePrismaticSectionAuthorityCount+receipt.ActiveSourceStaticNodalLoadAuthorityCount!=receipt.ActiveSourceAuthorityCount{add("ACTIVE_SOURCE_AUTHORITY_COVERAGE_COUNT_MISMATCH")}
	if strings.TrimSpace(receipt.AuthorityCatalogRoot)==""{add("AUTHORITY_CATALOG_ROOT_EMPTY")}
	if !isSHA256(receipt.AuthoritySnapshotSHA256){add("AUTHORITY_SNAPSHOT_SHA256_INVALID")}
	if !isSHA256(receipt.MCTSHA256){add("MCT_SHA256_INVALID")}
	if !isSHA256(receipt.RuntimeConfigSHA256){add("RUNTIME_CONFIG_SHA256_INVALID")}
	if !isSHA256(receipt.OpenSeesExecutableSHA256){add("OPENSEES_EXECUTABLE_SHA256_INVALID")}
	if strings.TrimSpace(receipt.MCTPath)==""{add("MCT_PATH_EMPTY")}
	if strings.TrimSpace(receipt.RuntimeConfig)==""{add("RUNTIME_CONFIG_EMPTY")}
	if strings.TrimSpace(receipt.OpenSeesExecutable)==""{add("OPENSEES_EXECUTABLE_EMPTY")}
	if receipt.Solver!="OpenSees"{add("SOLVER_IDENTITY_MISMATCH")}
	if strings.TrimSpace(receipt.SolverVersion)==""{add("SOLVER_VERSION_EMPTY")}
	if receipt.SolverRawExitCode!=0{add("SOLVER_RAW_EXIT_CODE_NONZERO")}
	if !samePath(receipt.Workspace,workspace){add("WORKSPACE_RECEIPT_MISMATCH")}

	if strings.TrimSpace(receipt.MCTPath)!=""{actual,bytes,err:=sha256File(receipt.MCTPath);if err!=nil{add("MCT_READ_FAILED:"+err.Error())}else{if bytes<=0{add("MCT_EMPTY")};if !strings.EqualFold(actual,receipt.MCTSHA256){add("MCT_FILE_SHA256_MISMATCH")};if !strings.EqualFold(actual,receipt.ActiveSourceSHA256){add("ACTIVE_SOURCE_FILE_SHA256_MISMATCH")}}}
	if strings.TrimSpace(receipt.RuntimeConfig)!=""{actual,bytes,err:=sha256File(receipt.RuntimeConfig);if err!=nil{add("RUNTIME_CONFIG_READ_FAILED:"+err.Error())}else{if bytes<=0{add("RUNTIME_CONFIG_EMPTY_FILE")};if !strings.EqualFold(actual,receipt.RuntimeConfigSHA256){add("RUNTIME_CONFIG_FILE_SHA256_MISMATCH")}}}
	if strings.TrimSpace(receipt.OpenSeesExecutable)!=""{actual,bytes,err:=sha256File(receipt.OpenSeesExecutable);if err!=nil{add("OPENSEES_EXECUTABLE_READ_FAILED:"+err.Error())}else{if bytes<=0{add("OPENSEES_EXECUTABLE_EMPTY_FILE")};if !strings.EqualFold(actual,receipt.OpenSeesExecutableSHA256){add("OPENSEES_EXECUTABLE_FILE_SHA256_MISMATCH")}}}

	if result.SchemaVersion!=AIOpenSeesResultSchema{add("ANALYSIS_RESULT_SCHEMA_MISMATCH")}
	if result.Status!="complete"{add("ANALYSIS_STATUS_NOT_COMPLETE")}
	if result.Solver!="OpenSees"{add("ANALYSIS_SOLVER_IDENTITY_MISMATCH")}
	if strings.TrimSpace(result.SolverVersion)==""{add("ANALYSIS_SOLVER_VERSION_EMPTY")}
	if result.RawExitCode!=0{add("ANALYSIS_RAW_EXIT_CODE_NONZERO")}
	if result.Solver!=receipt.Solver{add("SOLVER_IDENTITY_CROSS_BIND_MISMATCH")}
	if result.SolverVersion!=receipt.SolverVersion{add("SOLVER_VERSION_CROSS_BIND_MISMATCH")}
	if result.RawExitCode!=receipt.SolverRawExitCode{add("SOLVER_EXIT_CODE_CROSS_BIND_MISMATCH")}
	if !result.AuthorityRuntimeUsed{add("ANALYSIS_AUTHORITY_RUNTIME_NOT_USED")}
	if !samePath(result.SourcePath,receipt.MCTPath){add("ANALYSIS_SOURCE_PATH_MISMATCH")}
	if !strings.EqualFold(result.SourceSHA256,receipt.MCTSHA256){add("SOURCE_SHA256_MISMATCH")}
	if !strings.EqualFold(result.SourceSHA256,receipt.ActiveSourceSHA256){add("ANALYSIS_ACTIVE_SOURCE_SHA256_MISMATCH")}
	if !samePath(result.AuthorityConfigPath,receipt.RuntimeConfig){add("ANALYSIS_RUNTIME_CONFIG_PATH_MISMATCH")}
	if !samePath(result.SolverExecutable,receipt.OpenSeesExecutable){add("ANALYSIS_OPENSEES_EXECUTABLE_PATH_MISMATCH")}
	if result.AuthorityGeneration!=receipt.AuthorityGeneration{add("AUTHORITY_GENERATION_MISMATCH")}
	if !samePath(result.AuthorityCatalogRoot,receipt.AuthorityCatalogRoot){add("ANALYSIS_CATALOG_ROOT_MISMATCH")}
	if result.AuthorityEntryCount!=receipt.AuthorityEntryCount{add("ANALYSIS_ENTRY_COUNT_MISMATCH")}
	if !isSHA256(result.AuthoritySnapshotSHA256)||!strings.EqualFold(result.AuthoritySnapshotSHA256,receipt.AuthoritySnapshotSHA256){add("ANALYSIS_SNAPSHOT_SHA256_MISMATCH")}

	if runtime.SchemaVersion!=AIOpenSeesRuntimeSchema{add("AUTHORITY_RUNTIME_SCHEMA_MISMATCH")}
	if !runtime.Ready||!runtime.SnapshotValid{add("AUTHORITY_RUNTIME_NOT_READY")}
	if !samePath(runtime.ConfigPath,receipt.RuntimeConfig){add("RUNTIME_CONFIG_PATH_MISMATCH")}
	if runtime.Generation!=receipt.AuthorityGeneration{add("RUNTIME_GENERATION_MISMATCH")}
	if !samePath(runtime.CatalogRoot,receipt.AuthorityCatalogRoot){add("RUNTIME_CATALOG_ROOT_MISMATCH")}
	if runtime.EntryCount!=receipt.AuthorityEntryCount{add("RUNTIME_ENTRY_COUNT_MISMATCH")}
	if runtime.ElasticMaterialAuthorityCount!=receipt.ElasticMaterialAuthorityCount{add("RUNTIME_MATERIAL_AUTHORITY_COUNT_MISMATCH")}
	if runtime.PrismaticSectionAuthorityCount!=receipt.PrismaticSectionAuthorityCount{add("RUNTIME_SECTION_AUTHORITY_COUNT_MISMATCH")}
	if runtime.StaticNodalLoadAuthorityCount!=receipt.StaticNodalLoadAuthorityCount{add("RUNTIME_STATIC_NODAL_LOAD_AUTHORITY_COUNT_MISMATCH")}
	if runtime.ElasticMaterialAuthorityCount+runtime.PrismaticSectionAuthorityCount+runtime.StaticNodalLoadAuthorityCount!=runtime.EntryCount{add("RUNTIME_AUTHORITY_COVERAGE_COUNT_MISMATCH")}
	if !runtime.ActiveSourceCoverageValid{add("RUNTIME_ACTIVE_SOURCE_AUTHORITY_COVERAGE_INVALID")}
	if !runtime.ActiveSourceCohortValid{add("RUNTIME_ACTIVE_SOURCE_CIVIL_COHORT_INVALID")}
	if !runtime.ActiveSourceExportProvenanceValid{add("RUNTIME_ACTIVE_SOURCE_GUI_EXPORT_PROVENANCE_INVALID")}
	if strings.TrimSpace(runtime.ActiveSourceCivilVersion)==""{add("RUNTIME_ACTIVE_SOURCE_CIVIL_VERSION_EMPTY")}
	if strings.TrimSpace(runtime.ActiveSourceCivilBuild)==""{add("RUNTIME_ACTIVE_SOURCE_CIVIL_BUILD_EMPTY")}
	if runtime.ActiveSourceCivilVersion!=receipt.ActiveSourceCivilVersion{add("ACTIVE_SOURCE_CIVIL_VERSION_CROSS_BIND_MISMATCH")}
	if runtime.ActiveSourceCivilBuild!=receipt.ActiveSourceCivilBuild{add("ACTIVE_SOURCE_CIVIL_BUILD_CROSS_BIND_MISMATCH")}
	if runtime.ActiveSourceExportedAt!=receipt.ActiveSourceExportedAt{add("ACTIVE_SOURCE_EXPORTED_AT_CROSS_BIND_MISMATCH")}
	if runtime.ActiveSourceExportMethod!=receipt.ActiveSourceExportMethod{add("ACTIVE_SOURCE_EXPORT_METHOD_CROSS_BIND_MISMATCH")}
	if runtime.ActiveSourceExportProvenanceValid!=receipt.ActiveSourceExportProvenanceValid{add("ACTIVE_SOURCE_EXPORT_PROVENANCE_CROSS_BIND_MISMATCH")}
	if !strings.EqualFold(runtime.ActiveSourceSHA256,receipt.ActiveSourceSHA256){add("RUNTIME_ACTIVE_SOURCE_SHA256_MISMATCH")}
	if runtime.ActiveSourceAuthorityCount!=receipt.ActiveSourceAuthorityCount{add("RUNTIME_ACTIVE_SOURCE_AUTHORITY_COUNT_MISMATCH")}
	if runtime.ActiveSourceElasticMaterialAuthorityCount!=receipt.ActiveSourceElasticMaterialAuthorityCount{add("RUNTIME_ACTIVE_SOURCE_MATERIAL_AUTHORITY_COUNT_MISMATCH")}
	if runtime.ActiveSourcePrismaticSectionAuthorityCount!=receipt.ActiveSourcePrismaticSectionAuthorityCount{add("RUNTIME_ACTIVE_SOURCE_SECTION_AUTHORITY_COUNT_MISMATCH")}
	if runtime.ActiveSourceStaticNodalLoadAuthorityCount!=receipt.ActiveSourceStaticNodalLoadAuthorityCount{add("RUNTIME_ACTIVE_SOURCE_STATIC_NODAL_LOAD_AUTHORITY_COUNT_MISMATCH")}
	if runtime.ActiveSourceElasticMaterialAuthorityCount+runtime.ActiveSourcePrismaticSectionAuthorityCount+runtime.ActiveSourceStaticNodalLoadAuthorityCount!=runtime.ActiveSourceAuthorityCount{add("RUNTIME_ACTIVE_SOURCE_AUTHORITY_COVERAGE_COUNT_MISMATCH")}
	if !isSHA256(runtime.SnapshotSHA256)||!strings.EqualFold(runtime.SnapshotSHA256,receipt.AuthoritySnapshotSHA256){add("RUNTIME_SNAPSHOT_SHA256_MISMATCH")}

	artifactByName:=map[string]AIOpenSeesArtifact{}
	for _,artifact:=range receipt.Artifacts{if artifact.Name==""||artifact.Path==""||!isSHA256(artifact.SHA256){add("ARTIFACT_RECEIPT_INVALID:"+artifact.Name);continue};if _,exists:=artifactByName[artifact.Name];exists{add("ARTIFACT_RECEIPT_DUPLICATE:"+artifact.Name);continue};artifactByName[artifact.Name]=artifact}
	required:=[]string{"analysis-result.json","analysis-geometry.json","analysis-deformed.obj","analysis-deformation.svg","analysis.tcl","node_displacements.csv","node_reactions.csv","opensees.stdout.log","opensees.stderr.log","authority-runtime-state.json"}
	for _,name:=range required{artifact,ok:=artifactByName[name];if !ok{add("ARTIFACT_RECEIPT_MISSING:"+name);continue};expected:=filepath.Join(workspace,name);if !samePath(artifact.Path,expected){add("ARTIFACT_PATH_MISMATCH:"+name);continue};hash,bytes,err:=sha256File(expected);if err!=nil{add("ARTIFACT_READ_FAILED:"+name);continue};if hash!=strings.ToLower(artifact.SHA256){add("ARTIFACT_SHA256_MISMATCH:"+name);continue};if bytes!=artifact.Bytes{add("ARTIFACT_SIZE_MISMATCH:"+name);continue};if bytes==0&&name!="opensees.stdout.log"&&name!="opensees.stderr.log"{add("ARTIFACT_EMPTY:"+name);continue};report.VerifiedArtifacts++}
	checks:=[]struct{name,path,hash string}{{"analysis.tcl",result.ScriptPath,result.ScriptSHA256},{"opensees.stdout.log",result.StdoutPath,result.StdoutSHA256},{"opensees.stderr.log",result.StderrPath,result.StderrSHA256},{"analysis-geometry.json",result.GeometryJSONPath,result.GeometryJSONSHA256},{"analysis-deformed.obj",result.DeformedOBJPath,result.DeformedOBJSHA256},{"analysis-deformation.svg",result.DeformationSVGPath,result.DeformationSVGSHA256},{"node_displacements.csv",result.DisplacementCSVPath,result.DisplacementCSVSHA256},{"node_reactions.csv",result.ReactionCSVPath,result.ReactionCSVSHA256}}
	for _,check:=range checks{artifact,ok:=artifactByName[check.name];if !ok{continue};if !samePath(check.path,filepath.Join(workspace,check.name)){add("ANALYSIS_ARTIFACT_PATH_MISMATCH:"+check.name)};if !isSHA256(check.hash)||strings.ToLower(check.hash)!=strings.ToLower(artifact.SHA256){add("ANALYSIS_ARTIFACT_SHA256_MISMATCH:"+check.name)}}
	report.Accepted=len(report.Blockers)==0&&report.VerifiedArtifacts==len(required)
	return report
}
