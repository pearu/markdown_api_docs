import os
import sys
import markdown_api_docs as mad
from markdown_api_docs.source_reader import _filter_cpp_data as filter_cpp_data
from markdown_api_docs.source_reader import _apply_cpp_macro as apply_cpp_macro
from markdown_api_docs.source_reader import _apply_cpp_macro_to_text as apply_cpp_macro_to_text
from markdown_api_docs.spanstr import spanstr


def flatten(lst):
  if isinstance(lst, list):
    for item in lst:
      yield from flatten(item)
  else:
    yield lst

def main():
    path = sys.argv[1]
    print(f'{path=}')

    def apply_onread(text):
        text = apply_cpp_macro_to_text(text, "TF_ASSIGN_OR_RETURN", lambda lhs, rexpr, statusor="_status_or_value_PHONY": f'auto {statusor} = {rexpr}; if (TF_PREDICT_FALSE(!{statusor}.ok())) {{ return {statusor}.status(); }} {lhs} = std::move({statusor}).value()')
        text = apply_cpp_macro_to_text(text, "MOCK_METHOD", lambda *args: '')
        text = apply_cpp_macro_to_text(text, "NB_OBJECT_DEFAULT", lambda *args: '')  # todo
        text = apply_cpp_macro_to_text(text, "TF_ASSERT_OK_AND_ASSIGN", lambda *args: '')  # todo
        text = apply_cpp_macro_to_text(text, "ABSL_DEPRECATED", lambda *args: '')
        text = apply_cpp_macro_to_text(text, "EIGEN_STATIC_ASSERT", lambda *args: '')
        text = apply_cpp_macro_to_text(text, "NB_TYPE_CASTER", lambda Value_, descr: '')
        text = apply_cpp_macro_to_text(text, 'NVML_FUNCTOR', lambda name, rettype, args: f'inline {rettype}(*xla_{name}) {args} = nullptr;')

        return text
    
    tree = mad.source_reader(path, stop_at_stage = 'after_filter_comments', apply_onread=apply_onread)
    if os.path.isfile(path):
      tree = [(path, tree)]
    success = 0
    failure= 0
    errors = 0
    data = set()
    files_with_errors = []
    files_with_failures = []
    for i, (fn, (source_lines, comments)) in enumerate(flatten(tree)):

      if fn.endswith('xla/tsl/platform/profile_utils/cpu_utils.h'):  # contains __asm__ volatile
          continue
      if fn.endswith('xla/tsl/concurrency/async_value_ref.h') or fn.endswith('xla/backends/cpu/runtime/thunk_executor.h'):
          # Uses:
          """
          int a = 
          #if defined(...)
            1;
          #else
            2;
          #endif
          """
          continue

        
      ctx = mad.parser.Context(enable_debug_rerun=not True, debug=not True, source=fn)
      print(fn)

      source_lines, cpp_data = filter_cpp_data(source_lines)
      source_lines = apply_cpp_macro(source_lines, "ABSL_DEPRECATED", lambda *args: '')
      source_lines = apply_cpp_macro(source_lines, "ABSL_EXCLUSIVE_LOCKS_REQUIRED", lambda *args: '')
      source_lines = apply_cpp_macro(source_lines, "ABSL_SHARED_LOCKS_REQUIRED", lambda *args: '')
      source_lines = apply_cpp_macro(source_lines, "ABSL_LOCKS_EXCLUDED", lambda *args: '')
      source_lines = apply_cpp_macro(source_lines, "TF_GUARDED_BY", lambda *args: '')
      source_lines = apply_cpp_macro(source_lines, "TF_EXCLUSIVE_LOCKS_REQUIRED", lambda *args: '')
      source_lines = apply_cpp_macro(source_lines, "TF_ACQUIRED_AFTER", lambda *args: '')
      source_lines = apply_cpp_macro(source_lines, "TF_DEFINE_CHECK_OP_IMPL", lambda *args: '')
      source_lines = apply_cpp_macro(source_lines, "TF_LOCKS_EXCLUDED", lambda *args: '')
      source_lines = apply_cpp_macro(source_lines, "HLO_OPCODE_LIST", lambda *args: '')
      
      
      source_lines = apply_cpp_macro(source_lines, "ABSL_GUARDED_BY", lambda *args: '')
      source_lines = apply_cpp_macro(source_lines, "HLO_MATCHER", lambda opcode: f'template <typename... M> ::testing::Matcher<const ::xla::HloInstruction*> {opcode}(M... operands)')
      source_lines = apply_cpp_macro(source_lines, "ABSL_ATTRIBUTE_NOINLINE", '')
      source_lines = apply_cpp_macro(source_lines, "ABSL_MUST_USE_RESULT", '')
      source_lines = apply_cpp_macro(source_lines, "TF_ATTRIBUTE_NOINLINE", '')
      source_lines = apply_cpp_macro(source_lines, "TF_CONST_INIT", '')
      source_lines = apply_cpp_macro(source_lines, "ABSL_ATTRIBUTE_PACKED", '')
      source_lines = apply_cpp_macro(source_lines, "TF_ATTRIBUTE_COLD", '')
      source_lines = apply_cpp_macro(source_lines, "TF_ATTRIBUTE_NORETURN", '')
      source_lines = apply_cpp_macro(source_lines, "TF_MUST_USE_RESULT", '')
      source_lines = apply_cpp_macro(source_lines, "ABSL_CONST_INIT", '')
      source_lines = apply_cpp_macro(source_lines, "__restrict", '')
      source_lines = apply_cpp_macro(source_lines, "TF_EXPORT", '')

      source_lines = apply_cpp_macro(source_lines, "NB_OBJECT", lambda Type, Parent, Str, Check: f'public: static constexpr auto Name = ::nanobind::detail::const_name({Str}); {Type}(handle h, ::nanobind::detail::borrow_t) : {Parent}(h, ::nanobind::detail::borrow_t{{}}) {{}} {Type}(handle h, ::nanobind::detail::steal_t) : {Parent}(h, ::nanobind::detail::steal_t{{}}) {{}} static bool check_(handle h) {{ return {Check}(h.ptr()); }}')

      for m, b in [('ABSL_DEPRECATE_AND_INLINE', lambda *args: ''),
                   ('INT_TYPE_ASSIGNMENT_OP', lambda *args: ''),  # todo
                   ('INT_TYPE_ARITHMETIC_OP', lambda *args: ''),  # todo
                   ('INT_TYPE_COMPARISON_OP', lambda *args: ''),  # todo
                   ('EIGEN_STATIC_ASSERT', lambda *args: ''),
                   ('MAP_STABLEHLO_TO_HLO', lambda *args: f'template <> struct HloToStablehloOpImpl<mhlo::{args[0]}> {{ using Type = stablehlo::{args[0]};  }};  template <> struct StablehloToHloOpImpl<stablehlo::{args[0]}> {{ using Type = mhlo::{args[0]};   }};'),
                   ('FOREACH_HIPSPARSE_ROCM42_API', lambda *args: ''), #todo
                   ('FOREACH_HIPSPARSE_API', lambda *args: ''), #todo
                   ('FOREACH_HIPSOLVER_API', lambda *args: ''), #todo
                   ('FOREACH_ROCTRACER_API', lambda *args: ''), #todo
                   ('FOREACH_HIPBLASLT_API', lambda *args: ''), #todo
                   ('FOREACH_ROCBLAS_API', lambda *args: ''), #todo
                   ('HIP_ROUTINE_EACH', lambda *args: ''), #todo
                   ('FOREACH_ROCSOLVER_API', lambda *args: ''), #todo
                   ('HIP_ROUTINE_EACH_62', lambda *args: ''), #todo
                   ('ABSL_PT_GUARDED_BY', lambda *args: ''),
                   ('NB_OBJECT_DEFAULT', lambda *args: ''),  # todo
                   ('MAP_IFRT_TO_VIFRT', lambda *args: ''),
                   ('MAP_OTHER_TO_VIFRT', lambda *args: ''),
                   ('XLA_CUB_DECLARE_SORT_KEYS', lambda *args: ''),
                   ('XLA_CUB_DECLARE_SORT_PAIRS', lambda *args: ''),
                   ('ABSL_EXCLUSIVE_LOCK_FUNCTION', lambda *args: ''),
                   ('ABSL_UNLOCK_FUNCTION', lambda *args: ''),
                   ('DEFINE_WRAPPER', lambda *args: ''),
                   ('XLA_NULLOP_PATTERN', lambda *args: ''), # todo
                   ('XLA_COMMUTATIVE_BINOP_PATTERN', lambda *args: ''), # todo
                   ('XLA_UNOP_PATTERN', lambda *args: ''), # todo
                   ('XLA_BINOP_PATTERN', lambda *args: ''), # todo
                   ('XLA_TERNOP_PATTERN', lambda *args: ''), # todo
                   ('XLA_VARIADIC_OP_PATTERN', lambda *args: ''), # todo
                   ('XLA_COMMUTATIVE_COMPARE_PATTERN', lambda *args: ''), # todo
                   ('XLA_COMPARE_PATTERN', lambda *args: ''), # todo
                   ('XLA_FUZZY_UNOP_PATTERN', lambda *args: ''), # todo
                   ('XLA_FUZZY_BINOP_PATTERN', lambda *args: ''), # todo
                   ('XLA_FUZZY_TERNOP_PATTERN', lambda *args: ''), # todo
                   ('COMMAND_BUFFER_CMD_LIST', lambda *args: ''), # todo
                   ('__launch_bounds__', lambda *args: ''), # todo
                   ('MATCHER', lambda Matcher, description: f'void name{Matcher} ()'),
                   ('MATCHER_P', lambda Matcher, p0, description: f'void name{Matcher}{p0} ()'),

                
                ]:
          source_lines = apply_cpp_macro(source_lines, m, b)
      
      
      source_lines = apply_cpp_macro(source_lines, "ABSL_ATTRIBUTE_ALWAYS_INLINE", '')
      #source_lines = apply_cpp_macro(source_lines, 'NT', '')
      for m in ['EIGEN_STRONG_INLINE', 'EIGEN_DEBUG_UNALIGNED_LOAD', 'EIGEN_DEBUG_ALIGNED_LOAD', 'PHILOX_DEVICE_INLINE',
                'ABSL_NO_THREAD_SAFETY_ANALYSIS', 'EIGEN_DEVICE_FUNC', 'EIGEN_ALWAYS_INLINE',
                'EIGEN_ALIGN_MAX', 'EIGEN_DONT_INLINE', 'EIGEN_SCALAR_BINARY_OP_PLUGIN', 'MLIR_CAPI_EXPORTED', 'XLA_FFI_ATTRIBUTE_ALWAYS_INLINE',
                'TENSORFLOW_STREAM_EXECUTOR_GPU_BLAS_SUPPORT_OVERRIDES',
                'TENSORFLOW_STREAM_EXECUTOR_GPU_FFT_SUPPORT_OVERRIDES',
                'TFTPU_CAPI_EXPORT', 'ABSL_ATTRIBUTE_LIFETIME_BOUND',
                'XLA_UNROLL', 'XLA_FLATTEN', 'PJRT_CAPI_EXPORT',
                '__device__', '__forceinline__', '__shared__ ', '__global__',
                'CUTLASS_HOST_DEVICE', 'CUTLASS_DEVICE', 'CUTLASS_PRAGMA_UNROLL',
                'FORCEINLINE',
                ]:
          source_lines = apply_cpp_macro(source_lines, m, '')
      
      # source_lines = apply_cpp_macro(source_lines, "TF_ASSIGN_OR_RETURN", lambda lhs, rexpr: f'TF_ASSIGN_OR_RETURN_IMPL(_status_or_value_PHONY, {lhs}, {rexpr})')
      # source_lines = apply_cpp_macro(source_lines, "TF_ASSIGN_OR_RETURN", lambda lhs, rexpr, statusor="_status_or_value_PHONY": f'auto {statusor} = ({rexpr}); if (TF_PREDICT_FALSE(!{statusor}.ok())) {{ return {statusor}.status(); }} {lhs} = std::move({statusor}).value()')

      source = ''
      for lineno, line in source_lines.items():
        source += line + '\n'
      source = f'{source}'
      if source.strip() == '': continue

      source = spanstr(source).lstrip()

      """
      k = 0
      while k != -1:
          k = source.find('>', k)
          if k != -1:
              s = source[k:k+2].data
              next = source[k+1:].lstrip().data[0:1]
              prev = source[max(0, k-1)].data
              k += 1
              if next:
                  if next in '&>,;*:=){."[}':
                      continue
                  if s[1] in ' \n':
                      continue
                  if prev in '-':
                      continue
                  assert next == '(', next
              print(repr(source[max(0, k-10):k].data), repr(source[k:k+10].data))
              data.add(s)
      """

      print(f'------------ source of {fn=} ---------------')
      print(source)
      print(f'------------ end of source of {fn=} --------')
      try:
          tree, rest = mad.parser.translation_unit.split(ctx, source)
      except Exception as msg:
          print(msg)
          errors += 1
          print(f'{success=} {failure=} {errors=}')
          raise
          files_with_errors.append(fn)
          continue
      if tree is not None:
        print(tree.tostring())
      print(f'{rest=}')

      print(ctx.block)
      if rest or tree is None:
          failure += 1
          files_with_failures.append(fn)
      else:
          success += 1
      print(f'{success=} {failure=} {errors=}')
      if tree is None:
        print('parse failure')
        #assert 0, rest
      if rest:
        print('incomplete parse')
        #assert 0, rest
    print(data)

    print('Files with errors:')
    print('\t' + '\n\t'.join(files_with_errors))
    print('Files with failures:')
    print('\t' + '\n\t'.join(files_with_failures))
    
if __name__ == "__main__":
  main()
