#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Google Model tool calls unified processor

Solve the problem of Google model result.content being empty when the tool is called,
Provides unified tool call processing logic for use by all analysts.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage

logger = logging.getLogger(__name__)

class GoogleToolCallHandler:
    """Google Model tool calls unified processor"""
    
    @staticmethod
    def is_google_model(llm) -> bool:
        """Check if it is a Google model"""
        return 'Google' in llm.__class__.__name__ or 'ChatGoogleOpenAI' in llm.__class__.__name__
    
    @staticmethod
    def handle_google_tool_calls(
        result: AIMessage,
        llm: Any,
        tools: List[Any],
        state: Dict[str, Any],
        analysis_prompt_template: str,
        analyst_name: str = "分析师"
    ) -> Tuple[str, List[Any]]:
        """
        Unified processing of tool calls for Google models
        
        Args:
            result: LLM The result of the first call
            llm: Language model example
            tools: List of available tools
            state: Current status
            analysis_prompt_template: Analysis Prompt Word Template
            analyst_name: Analyst name
            
        Returns:
            Tuple[str, List[Any]]: (analysis report, Message list)
        """
        
        # Validate input parameters
        logger.info(f"[{analyst_name}] 🔍 Start Google tool call processing...")
        logger.debug(f"[{analyst_name}] 🔍 LLM类型: {llm.__class__.__name__}")
        logger.debug(f"[{analyst_name}] 🔍 工具数量: {len(tools) if tools else 0}")
        logger.debug(f"[{analyst_name}] 🔍 状态类型: {type(state).__name__ if state else None}")
        
        if not GoogleToolCallHandler.is_google_model(llm):
            logger.warning(f"[{analyst_name}] ⚠️ Non-Google models, skip special handling")
            logger.debug(f"[{analyst_name}] 🔍 模型检查失败: {llm.__class__.__name__}")
            # Non-Google model, returns original content
            return result.content, [result]
        
        logger.info(f"[{analyst_name}] ✅ Confirmed as Google model")
        logger.debug(f"[{analyst_name}] 🔍 结果类型: {type(result).__name__}")
        logger.debug(f"[{analyst_name}] 🔍 结果属性: {[attr for attr in dir(result) if not attr.startswith('_')]}")
        
        # Check if API call is successful
        if not hasattr(result, 'content'):
            logger.error(f"[{analyst_name}] ❌ Google Model API call failed, no content returned")
            logger.debug(f"[{analyst_name}] 🔍 Result object is missing content property")
            return "Google Model API call failed", []
        
        # Check if there is a tool call
        if not hasattr(result, 'tool_calls'):
            logger.warning(f"[{analyst_name}] ⚠️ The result object has no tool_calls attribute")
            logger.debug(f"[{analyst_name}] 🔍 可用属性: {[attr for attr in dir(result) if not attr.startswith('_')]}")
            return result.content, [result]
        
        if not result.tool_calls:
            # Improvement: Provide more detailed diagnostic information
            logger.info(f"[{analyst_name}] ℹ️ Google The model does not call the tool, possible reasons:")
            logger.info(f"[{analyst_name}]   - Input message is empty or incorrectly formatted")
            logger.info(f"[{analyst_name}]   - The model does not think it is necessary to call the tool")
            logger.info(f"[{analyst_name}]   - There may be a problem with tool binding")
            
            # Check input message
            if "messages" in state:
                messages = state["messages"]
                if not messages:
                    logger.warning(f"[{analyst_name}] ⚠️ Input message list is empty")
                else:
                    logger.info(f"[{analyst_name}] 📝 输入消息数量: {len(messages)}")
                    for i, msg in enumerate(messages):
                        msg_type = type(msg).__name__
                        content_preview = str(msg.content)[:100] if hasattr(msg, 'content') else "无内容"
                        logger.info(f"[{analyst_name}]   消息 {i+1}: {msg_type} - {content_preview}...")
            
            # Check whether the content is an analysis report
            content = result.content
            logger.info(f"[{analyst_name}] 🔍 Check whether the returned content is an analysis report...")
            logger.debug(f"[{analyst_name}] 🔍 内容类型: {type(content)}")
            logger.debug(f"[{analyst_name}] 🔍 内容长度: {len(content) if content else 0}")
            
            # Check whether the content contains the characteristics of the analysis report
            is_analysis_report = False
            analysis_keywords = ["分析", "报告", "总结", "评估", "建议", "风险", "趋势", "市场", "股票", "投资"]
            
            if content:
                # Check content length and keywords
                if len(content) > 200:  # Assume analysis reports are at least 200 characters long
                    keyword_count = sum(1 for keyword in analysis_keywords if keyword in content)
                    is_analysis_report = keyword_count >= 3  # Contain at least 3 keywords
                
                logger.info(f"[{analyst_name}] 🔍 内容判断为{'分析报告' if is_analysis_report else '非分析报告'}")
                
                if is_analysis_report:
                    logger.info(f"[{analyst_name}] ✅ Google模型直接返回了分析报告，长度: {len(content)} 字符")
                    return content, [result]
            
            # Return original content but add description
            return result.content, [result]
        
        logger.info(f"[{analyst_name}] 🔧 Google模型调用了 {len(result.tool_calls)} 个工具")
        
        # Record tool call details
        for i, tool_call in enumerate(result.tool_calls):
            logger.info(f"[{analyst_name}] 工具 {i+1}:")
            logger.info(f"[{analyst_name}]   ID: {tool_call.get('id', 'N/A')}")
            logger.info(f"[{analyst_name}]   名称: {tool_call.get('name', 'N/A')}")
            logger.info(f"[{analyst_name}]   参数: {tool_call.get('args', {})}")
        
        try:
            # Execute tool call
            tool_messages = []
            tool_results = []
            executed_tools = set()  # Prevent repeated calls to the same tool
            
            logger.info(f"[{analyst_name}] 🔧 开始执行 {len(result.tool_calls)} 个工具调用...")
            
            # Verification tool calling format
            valid_tool_calls = []
            for i, tool_call in enumerate(result.tool_calls):
                if GoogleToolCallHandler._validate_tool_call(tool_call, i, analyst_name):
                    valid_tool_calls.append(tool_call)
                else:
                    # Try fix tool call
                    fixed_tool_call = GoogleToolCallHandler._fix_tool_call(tool_call, i, analyst_name)
                    if fixed_tool_call:
                        valid_tool_calls.append(fixed_tool_call)
            
            logger.info(f"[{analyst_name}] 🔧 有效工具调用: {len(valid_tool_calls)}/{len(result.tool_calls)}")
            
            for i, tool_call in enumerate(valid_tool_calls):
                tool_name = tool_call.get('name')
                tool_args = tool_call.get('args', {})
                tool_id = tool_call.get('id')
                
                # Prevent repeated calls to the same tool (especially unified market data tools)
                tool_signature = f"{tool_name}_{hash(str(tool_args))}"
                if tool_signature in executed_tools:
                    logger.warning(f"[{analyst_name}] ⚠️ Skip duplicate tool calls: {tool_name}")
                    continue
                executed_tools.add(tool_signature)
                
                logger.info(f"[{analyst_name}] 🛠️ 执行工具 {i+1}/{len(valid_tool_calls)}: {tool_name}")
                logger.info(f"[{analyst_name}] 参数: {tool_args}")
                logger.debug(f"[{analyst_name}] 🔧 工具调用详情: {tool_call}")
                
                # Find the corresponding tool and execute it
                tool_result = None
                available_tools = []
                
                for tool in tools:
                    current_tool_name = GoogleToolCallHandler._get_tool_name(tool)
                    available_tools.append(current_tool_name)
                    
                    if current_tool_name == tool_name:
                        try:
                            logger.debug(f"[{analyst_name}] 🔧 找到工具: {tool.__class__.__name__}")
                            logger.debug(f"[{analyst_name}] 🔧 Tool type checking...")
                            
                            # Check tool type and call accordingly
                            if hasattr(tool, 'invoke'):
                                # LangChain Tools, use the invoke method
                                logger.info(f"[{analyst_name}] 🚀 Calling LangChain tool.invoke()...")
                                tool_result = tool.invoke(tool_args)
                                logger.info(f"[{analyst_name}] ✅ LangChain工具执行成功，结果长度: {len(str(tool_result))} 字符")
                                logger.debug(f"[{analyst_name}] 🔧 工具结果类型: {type(tool_result)}")
                            elif callable(tool):
                                # Ordinary Python function, called directly
                                logger.info(f"[{analyst_name}] 🚀 Calling Python function tool...")
                                tool_result = tool(**tool_args)
                                logger.info(f"[{analyst_name}] ✅ Python函数工具执行成功，结果长度: {len(str(tool_result))} 字符")
                                logger.debug(f"[{analyst_name}] 🔧 工具结果类型: {type(tool_result)}")
                            else:
                                logger.error(f"[{analyst_name}] ❌ 工具类型不支持: {type(tool)}")
                                tool_result = f"工具类型不支持: {type(tool)}"
                            break
                        except Exception as tool_error:
                            logger.error(f"[{analyst_name}] ❌ 工具执行失败: {tool_error}")
                            logger.error(f"[{analyst_name}] ❌ 异常类型: {type(tool_error).__name__}")
                            logger.error(f"[{analyst_name}] ❌ 异常详情: {str(tool_error)}")
                            
                            # Log detailed exception stack
                            import traceback
                            error_traceback = traceback.format_exc()
                            logger.error(f"[{analyst_name}] ❌ Tool execution exception stack:\n{error_traceback}")
                            
                            tool_result = f"工具执行失败: {str(tool_error)}"
                
                logger.debug(f"[{analyst_name}] 🔧 可用工具列表: {available_tools}")
                
                if tool_result is None:
                    tool_result = f"未找到工具: {tool_name}"
                    logger.warning(f"[{analyst_name}] ⚠️ 未找到工具: {tool_name}")
                    logger.debug(f"[{analyst_name}] ⚠️ 工具名称不匹配，期望: {tool_name}, 可用: {available_tools}")
                
                # Create tool message
                tool_message = ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_id
                )
                tool_messages.append(tool_message)
                tool_results.append(tool_result)
                logger.debug(f"[{analyst_name}] 🔧 create tool messages,ID: {tool_message.tool_call_id}")
            
            logger.info(f"[{analyst_name}] 🔧 工具调用完成，成功: {len(tool_results)}, 总计: {len(result.tool_calls)}")
            
            # Call the model for the second time to generate the final analysis report
            logger.info(f"[{analyst_name}] 🚀 Generate final analysis report based on tool results...")
            
            # 🔧 [Optimize] Do not accumulate historical messages, only retain the messages required for current analysis
            # Reason:
            # 1. Fundamental analysts do not need historical news from other analysts
            # 2. Avoid messages that are too long (previously accumulated to 55,096 characters)
            # 3. Reduce token consumption and costs
            # 4. Subsequently, the Research Manager will be responsible for synthesizing all analysts' reports.
            safe_messages = []

            # Only keep the initial user message (if any)
            if "messages" in state and state["messages"]:
                # Only keep the first HumanMessage (usually the initial task description)
                for msg in state["messages"]:
                    if isinstance(msg, HumanMessage):
                        safe_messages.append(msg)
                        logger.debug(f"[{analyst_name}] 📝 保留初始用户消息")
                        break

            # Add current results (AI tool call)
            if hasattr(result, 'content'):
                safe_messages.append(result)
                logger.debug(f"[{analyst_name}] 📝 Add AI tool call message")

            # Add tool message (tool execution result)
            safe_messages.extend(tool_messages)
            logger.debug(f"[{analyst_name}] 📝 添加 {len(tool_messages)} 条工具消息")

            # Add analysis tips
            safe_messages.append(HumanMessage(content=analysis_prompt_template))
            logger.debug(f"[{analyst_name}] 📝 添加分析提示")
            
            # Record message sequence information
            total_length = sum(len(str(msg.content)) for msg in safe_messages if hasattr(msg, 'content'))
            logger.info(f"[{analyst_name}] 📊 消息序列: {len(safe_messages)} 条消息, 总长度: {total_length:,} 字符")
            
            # Check if the message sequence is empty
            if not safe_messages:
                logger.error(f"[{analyst_name}] ❌ The message sequence is empty and the analysis report cannot be generated.")
                tool_summary = "\n\n".join([f"工具结果 {i+1}:\n{str(result)}" for i, result in enumerate(tool_results)])
                report = f"{analyst_name}The tool call is completed and the following data is obtained:\n\n{tool_summary}"
                return report, [result] + tool_messages
            
            # Generate final analysis report
            try:
                logger.info(f"[{analyst_name}] 🔄 Start calling the Google model to generate the final analysis report...")
                logger.debug(f"[{analyst_name}] 📋 LLM类型: {llm.__class__.__name__}")
                logger.debug(f"[{analyst_name}] 📋 消息数量: {len(safe_messages)}")
                
                # Log the type and length of each message
                for i, msg in enumerate(safe_messages):
                    msg_type = msg.__class__.__name__
                    msg_length = len(str(msg.content)) if hasattr(msg, 'content') else 0
                    logger.debug(f"[{analyst_name}] 📋 消息 {i+1}: {msg_type}, 长度: {msg_length}")
                
                # Record the content of the analysis prompt (first 200 characters)
                analysis_msg = safe_messages[-1] if safe_messages else None
                if analysis_msg and hasattr(analysis_msg, 'content'):
                    prompt_preview = str(analysis_msg.content)[:200] + "..." if len(str(analysis_msg.content)) > 200 else str(analysis_msg.content)
                    logger.debug(f"[{analyst_name}] 📋 分析提示预览: {prompt_preview}")
                
                logger.info(f"[{analyst_name}] 🚀 Calling LLM.invoke()...")
                final_result = llm.invoke(safe_messages)
                logger.info(f"[{analyst_name}] ✅ LLM.invoke()Call completed")
                
                # Check the returned results in detail
                logger.debug(f"[{analyst_name}] 🔍 Check LLM return results...")
                logger.debug(f"[{analyst_name}] 🔍 返回结果类型: {type(final_result)}")
                logger.debug(f"[{analyst_name}] 🔍 返回结果属性: {dir(final_result)}")
                
                if hasattr(final_result, 'content'):
                    content = final_result.content
                    logger.debug(f"[{analyst_name}] 🔍 内容类型: {type(content)}")
                    logger.debug(f"[{analyst_name}] 🔍 内容长度: {len(content) if content else 0}")
                    logger.debug(f"[{analyst_name}] 🔍 内容是否为空: {not content}")
                    
                    if content:
                        content_preview = content[:200] + "..." if len(content) > 200 else content
                        logger.debug(f"[{analyst_name}] 🔍 内容预览: {content_preview}")
                        
                        report = content
                        logger.info(f"[{analyst_name}] ✅ Google模型最终分析报告生成成功，长度: {len(report)} 字符")
                        
                        # Return the complete message sequence
                        all_messages = [result] + tool_messages + [final_result]
                        return report, all_messages
                    else:
                        logger.warning(f"[{analyst_name}] ⚠️ Google The model returns empty content")
                        logger.debug(f"[{analyst_name}] 🔍 Empty content details: repr={repr(content)}")
                else:
                    logger.warning(f"[{analyst_name}] ⚠️ Google The model return result has no content attribute")
                    logger.debug(f"[{analyst_name}] 🔍 可用属性: {[attr for attr in dir(final_result) if not attr.startswith('_')]}")
                
                # If you get here, it means that the content is empty or has no content attribute.
                logger.warning(f"[{analyst_name}] ⚠️ Google Model final analysis report generation failed - content is empty")
                # Downgrade handling: Generate simple reports based on tool results
                tool_summary = "\n\n".join([f"工具结果 {i+1}:\n{str(result)}" for i, result in enumerate(tool_results)])
                report = f"{analyst_name}The tool call is completed and the following data is obtained:\n\n{tool_summary}"
                logger.info(f"[{analyst_name}] 🔄 使用降级报告，长度: {len(report)} 字符")
                return report, [result] + tool_messages
                
            except Exception as final_error:
                logger.error(f"[{analyst_name}] ❌ Final analysis report generation failed: {final_error}")
                logger.error(f"[{analyst_name}] ❌ 异常类型: {type(final_error).__name__}")
                logger.error(f"[{analyst_name}] ❌ 异常详情: {str(final_error)}")
                
                # Log detailed exception stack
                import traceback
                error_traceback = traceback.format_exc()
                logger.error(f"[{analyst_name}] ❌ 异常堆栈:\n{error_traceback}")
                
                # Downgrade handling: Generate simple reports based on tool results
                tool_summary = "\n\n".join([f"工具结果 {i+1}:\n{str(result)}" for i, result in enumerate(tool_results)])
                report = f"{analyst_name}The tool call is completed and the following data is obtained:\n\n{tool_summary}"
                logger.info(f"[{analyst_name}] 🔄 异常后使用降级报告，长度: {len(report)} 字符")
                return report, [result] + tool_messages
                
        except Exception as e:
            logger.error(f"[{analyst_name}] ❌ Google Model tool call processing failed: {e}")
            import traceback
            traceback.print_exc()
            
            # Downgrade processing: return tool call information
            tool_names = [tc.get('name', 'unknown') for tc in result.tool_calls]
            report = f"{analyst_name}调用了工具 {tool_names} 但处理失败: {str(e)}"
            return report, [result]
    
    @staticmethod
    def _get_tool_name(tool):
        """获取工具名称"""
        if hasattr(tool, 'name'):
            return tool.name
        elif hasattr(tool, '__name__'):
            return tool.__name__
        else:
            return str(tool)
    
    @staticmethod
    def _validate_tool_call(tool_call, index, analyst_name):
        """验证工具调用格式"""
        try:
            if not isinstance(tool_call, dict):
                logger.warning(f"[{analyst_name}] ⚠️ 工具调用 {index} 不是字典格式: {type(tool_call)}")
                return False
            
            # Check required fields
            required_fields = ['name', 'args', 'id']
            for field in required_fields:
                if field not in tool_call:
                    logger.warning(f"[{analyst_name}] ⚠️ 工具调用 {index} 缺少字段 '{field}': {tool_call}")
                    return False
            
            # Check tool name
            tool_name = tool_call.get('name')
            if not isinstance(tool_name, str) or not tool_name.strip():
                logger.warning(f"[{analyst_name}] ⚠️ 工具调用 {index} 工具名称无效: {tool_name}")
                return False
            
            # Check parameters
            tool_args = tool_call.get('args')
            if not isinstance(tool_args, dict):
                logger.warning(f"[{analyst_name}] ⚠️ 工具调用 {index} 参数不是字典格式: {type(tool_args)}")
                return False
            
            # Check ID
            tool_id = tool_call.get('id')
            if not isinstance(tool_id, str) or not tool_id.strip():
                logger.warning(f"[{analyst_name}] ⚠️ 工具调用 {index} ID无效: {tool_id}")
                return False
            
            logger.debug(f"[{analyst_name}] ✅ 工具调用 {index} 验证通过: {tool_name}")
            return True
            
        except Exception as e:
            logger.error(f"[{analyst_name}] ❌ 工具调用 {index} 验证异常: {e}")
            return False
    
    @staticmethod
    def _fix_tool_call(tool_call, index, analyst_name):
        """尝试修复工具调用格式"""
        try:
            logger.info(f"[{analyst_name}] 🔧 尝试修复工具调用 {index}: {tool_call}")
            
            if not isinstance(tool_call, dict):
                logger.warning(f"[{analyst_name}] ❌ Unable to fix non-dictionary formatted tool calls: {type(tool_call)}")
                return None
            
            fixed_tool_call = tool_call.copy()
            
            # Repair tool name
            if 'name' not in fixed_tool_call or not isinstance(fixed_tool_call['name'], str):
                if 'function' in fixed_tool_call and isinstance(fixed_tool_call['function'], dict):
                    # OpenAI format conversion
                    function_data = fixed_tool_call['function']
                    if 'name' in function_data:
                        fixed_tool_call['name'] = function_data['name']
                        if 'arguments' in function_data:
                            import json
                            try:
                                if isinstance(function_data['arguments'], str):
                                    fixed_tool_call['args'] = json.loads(function_data['arguments'])
                                else:
                                    fixed_tool_call['args'] = function_data['arguments']
                            except json.JSONDecodeError:
                                fixed_tool_call['args'] = {}
                else:
                    logger.warning(f"[{analyst_name}] ❌ 无法确定工具名称")
                    return None
            
            # Repair parameters
            if 'args' not in fixed_tool_call:
                fixed_tool_call['args'] = {}
            elif not isinstance(fixed_tool_call['args'], dict):
                try:
                    import json
                    if isinstance(fixed_tool_call['args'], str):
                        fixed_tool_call['args'] = json.loads(fixed_tool_call['args'])
                    else:
                        fixed_tool_call['args'] = {}
                except:
                    fixed_tool_call['args'] = {}
            
            # Repair ID
            if 'id' not in fixed_tool_call or not isinstance(fixed_tool_call['id'], str):
                import uuid
                fixed_tool_call['id'] = f"call_{uuid.uuid4().hex[:8]}"
            
            # Verify fixed tool calls
            if GoogleToolCallHandler._validate_tool_call(fixed_tool_call, index, analyst_name):
                logger.info(f"[{analyst_name}] ✅ 工具调用 {index} 修复成功: {fixed_tool_call['name']}")
                return fixed_tool_call
            else:
                logger.warning(f"[{analyst_name}] ❌ 工具调用 {index} 修复失败")
                return None
                
        except Exception as e:
            logger.error(f"[{analyst_name}] ❌ 工具调用 {index} 修复异常: {e}")
            return None
    
    @staticmethod
    def handle_simple_google_response(
        result: AIMessage,
        llm: Any,
        analyst_name: str = "分析师"
    ) -> str:
        """
        Handling simple Google model responses (no tool calls)
        
        Args:
            result: LLM Call result
            llm: Language model example
            analyst_name: Analyst name
            
        Returns:
            str: analysis report
        """
        
        if not GoogleToolCallHandler.is_google_model(llm):
            return result.content
        
        logger.info(f"[{analyst_name}] 📝 Google模型直接回复，长度: {len(result.content)} 字符")
        
        # Check the content length and process it if it is too long
        if len(result.content) > 15000:
            logger.warning(f"[{analyst_name}] ⚠️ Google The model output is too long and needs to be truncated....")
            return result.content[:10000] + "\n\n[Note: Content has been truncated to ensure readability]"
        
        return result.content
    
    @staticmethod
    def generate_final_analysis_report(llm, messages: List, analyst_name: str) -> str:
        """
        Generate final analysis report - enhanced version with support for retries and model switching
        
        Args:
            llm: LLM Example
            messages: Message list
            analyst_name: Analyst name
            
        Returns:
            str: analysis report
        """
        if not GoogleToolCallHandler.is_google_model(llm):
            logger.warning(f"⚠️ [{analyst_name}] Non-Google model, skips Google tool processor")
            return ""
        
        # Retry configuration
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"🔍 [{analyst_name}] ===== Final analysis report generation begins (try {attempt + 1}/{max_retries}) =====")
                logger.debug(f"🔍 [{analyst_name}] LLM类型: {type(llm).__name__}")
                logger.debug(f"🔍 [{analyst_name}] LLM模型: {getattr(llm, 'model', 'unknown')}")
                logger.debug(f"🔍 [{analyst_name}] 消息数量: {len(messages)}")
                
                # Log message type and length
                for i, msg in enumerate(messages):
                    msg_type = type(msg).__name__
                    if hasattr(msg, 'content'):
                        content_length = len(str(msg.content)) if msg.content else 0
                        logger.debug(f"🔍 [{analyst_name}] 消息{i+1}: {msg_type}, 长度: {content_length}")
                    else:
                        logger.debug(f"🔍 [{analyst_name}] 消息{i+1}: {msg_type}, 无content属性")
                
                # Build analysis tips - adjust based on number of attempts
                if attempt == 0:
                    analysis_prompt = f"""
                    Based on the results of the above tool calls, please{analyst_name}Generate a detailed analysis report.
                    
                    Requirements:
                    1. Comprehensive analysis of data returned by all tools
                    2. Provide clear research conclusions, risk assessments and follow-up observation points
                    3. Reports should be structured and easy to understand
                    4. Contains specific data support and analysis logic
                    
                    Please generate a complete analysis report:
                    """
                elif attempt == 1:
                    analysis_prompt = f"""
                    请简要分析{analyst_name}的工具调用结果并给出研究结论。
                    要求：简洁明了，包含关键数据、风险提示和观察点。
                    """
                else:
                    analysis_prompt = f"""
                    请为{analyst_name}提供一个简短的分析总结。
                    """
                
                logger.debug(f"🔍 [{analyst_name}] 分析提示预览: {analysis_prompt[:100]}...")
                
                # Optimize message sequence
                optimized_messages = GoogleToolCallHandler._optimize_message_sequence(messages, analysis_prompt)
                
                logger.info(f"[{analyst_name}] 🚀 Calling LLM.invoke() (try {attempt + 1}/{max_retries})...")
                
                # Call LLM to generate reports
                import time
                start_time = time.time()
                result = llm.invoke(optimized_messages)
                end_time = time.time()
                
                logger.info(f"[{analyst_name}] ✅ LLM.invoke()调用完成 (耗时: {end_time - start_time:.2f}秒)")
                
                # Check the returned results in detail
                logger.debug(f"🔍 [{analyst_name}] 返回结果类型: {type(result).__name__}")
                logger.debug(f"🔍 [{analyst_name}] 返回结果属性: {dir(result)}")
                
                if hasattr(result, 'content'):
                    content = result.content
                    logger.debug(f"🔍 [{analyst_name}] 内容类型: {type(content)}")
                    logger.debug(f"🔍 [{analyst_name}] 内容长度: {len(content) if content else 0}")
                    
                    if not content or len(content.strip()) == 0:
                        logger.warning(f"[{analyst_name}] ⚠️ Google The model returns empty content (try {attempt + 1}/{max_retries})")
                        
                        if attempt < max_retries - 1:
                            logger.info(f"[{analyst_name}] 🔄 等待{retry_delay}秒后重试...")
                            time.sleep(retry_delay)
                            continue
                        else:
                            logger.warning(f"[{analyst_name}] ⚠️ Google Model final analysis report generation failed - all retries returned empty content")
                            # Use the downgrade report
                            fallback_report = GoogleToolCallHandler._generate_fallback_report(messages, analyst_name)
                            logger.info(f"[{analyst_name}] 🔄 使用降级报告，长度: {len(fallback_report)} 字符")
                            return fallback_report
                    else:
                        logger.info(f"[{analyst_name}] ✅ 成功生成分析报告，长度: {len(content)} 字符")
                        return content
                else:
                    logger.error(f"[{analyst_name}] ❌ The returned result has no content attribute (try {attempt + 1}/{max_retries})")
                    
                    if attempt < max_retries - 1:
                        logger.info(f"[{analyst_name}] 🔄 等待{retry_delay}秒后重试...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        fallback_report = GoogleToolCallHandler._generate_fallback_report(messages, analyst_name)
                        logger.info(f"[{analyst_name}] 🔄 使用降级报告，长度: {len(fallback_report)} 字符")
                        return fallback_report
                        
            except Exception as e:
                logger.error(f"[{analyst_name}] ❌ LLM Call exception (try {attempt + 1}/{max_retries}): {e}")
                logger.error(f"[{analyst_name}] ❌ 异常类型: {type(e).__name__}")
                logger.error(f"[{analyst_name}] ❌ 完整异常信息:\n{traceback.format_exc()}")
                
                if attempt < max_retries - 1:
                    logger.info(f"[{analyst_name}] 🔄 等待{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                else:
                    # Use the downgrade report
                    fallback_report = GoogleToolCallHandler._generate_fallback_report(messages, analyst_name)
                    logger.info(f"[{analyst_name}] 🔄 使用降级报告，长度: {len(fallback_report)} 字符")
                    return fallback_report
        
        # If all retries fail, return a degradation report
        fallback_report = GoogleToolCallHandler._generate_fallback_report(messages, analyst_name)
        logger.info(f"[{analyst_name}] 🔄 所有重试失败，使用降级报告，长度: {len(fallback_report)} 字符")
        return fallback_report
    
    @staticmethod
    def _optimize_message_sequence(messages: List, analysis_prompt: str) -> List:
        """
        Optimize the message sequence to ensure it is within a reasonable length
        
        Args:
            messages: Original message list
            analysis_prompt: Analysis Tips
            
        Returns:
            List: Optimized message list
        """
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
        
        # Calculate total length
        total_length = sum(len(str(msg.content)) for msg in messages if hasattr(msg, 'content'))
        total_length += len(analysis_prompt)
        
        if total_length <= 50000:
            # Reasonable length, add analysis tips directly
            return messages + [HumanMessage(content=analysis_prompt)]
        
        # Needs optimization: retain key messages
        optimized_messages = []
        
        # Keep last user message
        for msg in messages:
            if isinstance(msg, HumanMessage):
                optimized_messages = [msg]
                break
        
        # Keep AI messages and tool messages, but truncate overly long content
        for msg in messages:
            if isinstance(msg, (AIMessage, ToolMessage)):
                if hasattr(msg, 'content') and len(str(msg.content)) > 5000:
                    # Truncate overly long content
                    truncated_content = str(msg.content)[:5000] + "\n\n[Note: Data has been truncated to ensure processing efficiency]"
                    if isinstance(msg, AIMessage):
                        optimized_msg = AIMessage(content=truncated_content)
                    else:
                        optimized_msg = ToolMessage(
                            content=truncated_content,
                            tool_call_id=getattr(msg, 'tool_call_id', 'unknown')
                        )
                    optimized_messages.append(optimized_msg)
                else:
                    optimized_messages.append(msg)
        
        # Add analysis tips
        optimized_messages.append(HumanMessage(content=analysis_prompt))
        
        return optimized_messages
    
    @staticmethod
    def _generate_fallback_report(messages: List, analyst_name: str) -> str:
        """
        Generate degradation report
        
        Args:
            messages: Message list
            analyst_name: Analyst name
            
        Returns:
            str: downgrade report
        """
        from langchain_core.messages import ToolMessage
        
        # Extract tool results
        tool_results = []
        for msg in messages:
            if isinstance(msg, ToolMessage) and hasattr(msg, 'content'):
                content = str(msg.content)
                if len(content) > 1000:
                    content = content[:1000] + "\n\n[Note: Data has been truncated]"
                tool_results.append(content)
        
        if tool_results:
            tool_summary = "\n\n".join([f"工具结果 {i+1}:\n{result}" for i, result in enumerate(tool_results)])
            report = f"{analyst_name}The tool call is completed and the following data is obtained:\n\n{tool_summary}\n\n Note: Due to abnormal model response, this is a simplified report based on tool data."
        else:
            report = f"{analyst_name}The analysis was completed, but no valid tool data could be obtained. It is recommended to check the data source or try the analysis again."
        
        return report
    
    @staticmethod
    def create_analysis_prompt(
        ticker: str,
        company_name: str,
        analyst_type: str,
        specific_requirements: str = ""
    ) -> str:
        """
        Create standard analysis prompt words
        
        Args:
            ticker: Stock code
            company_name: Company name
            analyst_type: Analyst type (e.g."technical analysis", "fundamental analysis"etc.)
            specific_requirements: specific requirements
            
        Returns:
            str: Analyze prompt words
        """
        
        base_prompt = f"""现在请基于上述工具获取的数据，生成详细的{analyst_type}报告。

**股票信息：**
- 公司名称：{company_name}
- 股票代码：{ticker}

**分析要求：**
1. 报告必须基于工具返回的真实数据进行分析
2. 包含具体的数值和专业分析
3. 提供明确的研究结论、风险提示和后续观察点
4. 报告长度不少于800字
5. 使用中文撰写
6. 确保在分析中正确使用公司名称"{company_name}"和股票代码"{ticker}"

{specific_requirements}

请生成专业、详细的{analyst_type}报告，不得形成投资建议或交易指令。"""
        
        return base_prompt