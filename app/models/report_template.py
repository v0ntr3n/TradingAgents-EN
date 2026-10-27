"""
report template model

Supports configuring different report formats and output structures for different workflows.
Each workflow can be associated with a report template, which defines the report format produced by the workflow.

Usage scenarios:
- Preliminary process: concise pass/fail judgment report
- In-Depth Analysis: Detailed Investment Analysis Report
- Position Check: Position Risk Assessment Report
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from bson import ObjectId


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, *args, **kwargs):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, *args, **kwargs):
        return {"type": "string"}


class OutputField(BaseModel):
    """Report output field definitions"""
    name: str = Field(..., description="Field name")
    type: str = Field(..., description="Field type: string, number, boolean, array, object")
    description: str = Field("", description="Field description")
    required: bool = Field(True, description="Is it required?")
    default: Optional[Any] = Field(None, description="Default value")
    # For string types, you can define enumeration values
    enum: Optional[List[str]] = Field(None, description="Enumeration values (string type only)")
    # For number types, a range can be defined
    min_value: Optional[float] = Field(None, description="Minimum value (number type only)")
    max_value: Optional[float] = Field(None, description="Maximum value (number type only)")


class ReportTemplate(BaseModel):
    """
    report template model
    
    Define the report output format of the workflow, including:
    - Output field definition (output_schema)
    - Report generation prompt word (generator_prompt)
    - Summary and presentation configuration
    """
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    
    # Basic information
    template_id: str = Field(..., description="template unique identifier")
    name: str = Field(..., description="Template name")
    description: str = Field("", description="Template description")
    
    # Associated workflows
    workflow_id: str = Field(..., description="Associated workflows ID")
    
    # Output structure definition
    output_schema: List[OutputField] = Field(
        default_factory=list, 
        description="Report output field definitions"
    )
    
    # Report Generator Prompt Words
    generator_prompt: str = Field(
        "", 
        description="Prompt word template for LLM generated reports, available using {agent_outputs} equal variables"
    )
    
    # summary configuration
    summary_fields: List[str] = Field(
        default_factory=list,
        description="List of fields used to generate the summary"
    )
    
    # Display configuration
    display_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Front-end display configuration (field order, style, etc.)"
    )
    
    # Status
    status: str = Field("active", description="Status: active, inactive")
    
    # metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = Field(None, description="Creator user ID")
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class ReportTemplateCreate(BaseModel):
    """Create report template request"""
    template_id: str
    name: str
    description: str = ""
    workflow_id: str
    output_schema: List[OutputField] = Field(default_factory=list)
    generator_prompt: str = ""
    summary_fields: List[str] = Field(default_factory=list)
    display_config: Dict[str, Any] = Field(default_factory=dict)


class ReportTemplateUpdate(BaseModel):
    """Update report template request"""
    name: Optional[str] = None
    description: Optional[str] = None
    output_schema: Optional[List[OutputField]] = None
    generator_prompt: Optional[str] = None
    summary_fields: Optional[List[str]] = None
    display_config: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class ReportTemplateResponse(BaseModel):
    """report template response"""
    id: str
    template_id: str
    name: str
    description: str
    workflow_id: str
    output_schema: List[OutputField]
    generator_prompt: str
    summary_fields: List[str]
    display_config: Dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

