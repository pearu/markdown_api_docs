struct A {
public:
  explicit LLVMCommandLineOptionsLock(
      const std::vector<std::string>& client_options)
      ;
};
/*
int foo() {
  long unsigned int value = 1;
}

/*
template <typename T>
struct type_caster<absl::Span<T const>> {
  //int a = const_name("a[");
  NB_TYPE_CASTER(absl::Span<T const>,
                 
                 const_name("a[") + make_caster<T>::Name + const_name("]"))
  using Caster = make_caster<T>;


};


//enum class RocmTracerSyncTypes;
/*
struct XLA_FFI_State_Set_Args { void (*deleter)(void* state);
 void (*free_error)(JAX_InspectSharding_Callback_Args* args);
  template <typename C, typename... Args>  ThrowIfErrorWrapper(absl::Status (C::*)(Args...))   -> ThrowIfErrorWrapper<absl::Status(Args...), C>;

  explicit LLVMCommandLineOptionsLock(
      const std::vector<std::string>& client_options)
      ;
template <typename T>
    explicit Argument(absl::Span<const T> data);

};

int foo() {
  if (percentile < 0 || percentile > 100 || values_.empty()) {}

const Index spans[2][2] = {{0, patchIdSplit - patchId}, {patchIdSplit - patchId + 1, packetSize - 1}};

inline constexpr std::string_view kAddI32KernelPtx = R"(
.version 4.0
.target sm_50
)"

  long unsigned int value = static_cast<long unsigned int>(num_bytes);
bool matches[ 2][ 2];

 switch (s) {
 case se::dnn::DataType::kInt8: return se::dnn::DataType::kFloat;
 }
 fn(state, cast, extract_arg(Indices, (std::decay_t<T>*){nullptr})...);
 
}

  
/*

namespace mlir {
class OpBuilder;

namespace mhlo {



class MhloDialect : public Dialect {
 public:
  //explicit MhloDialect(MLIRContext *context);
  //static StringRef getDialectNamespace() { return "mhlo"; }
  Operation *materializeConstant(OpBuilder &builder, Attribute value, Type type, Location loc) override;

  LogicalResult verifyRegionArgAttribute(mlir::Operation *op,
                                         unsigned regionIndex,
                                         unsigned argIndex,
                                         mlir::NamedAttribute attr) override;
  LogicalResult verifyOperationAttribute(mlir::Operation *op,
                                         mlir::NamedAttribute attr) override;
  Type parseType(DialectAsmParser &parser) const override;
  void printType(Type type, DialectAsmPrinter &os) const override;
  Attribute parseAttribute(DialectAsmParser &parser, Type type) const override;
  void printAttribute(Attribute attr, DialectAsmPrinter &os) const override;
};
class TokenType : public Type::TypeBase<TokenType, Type, TypeStorage> {
 public:
  using Base::Base;
  static constexpr StringLiteral name = "mhlo.token";
};
void printConvolutionDimensions(AsmPrinter &p, ConvDimensionNumbersAttr dnums);
void printConvolutionDimensions(AsmPrinter &p, Operation *,
                                ConvDimensionNumbersAttr dnums);
ParseResult parseConvolutionDimensions(AsmParser &parser,
                                       ConvDimensionNumbersAttr &dnums);

}

  
}
/*
class A {
  auto operator*() -> HloInstructionInfo { return 1; };
};
/*
//int foo() { __asm__ volatile("rdtsc" : "=a"(low), "=d"(high)); }

  struct Alias {
    //Alias(int64_t parameter_number, ShapeIndex parameter_index, AliasKind kind = kMayAlias)
    //: parameter_number(parameter_number), parameter_index(std::move(parameter_index)), kind(kind)
    //{}

    Alias() {}
    
    //int64_t parameter_number;
    //ShapeIndex parameter_index;
    //AliasKind kind;

    //bool must_alias() const { return kind == kMustAlias; }
    /*
    std::string ToString() const {
      return absl::StrFormat("(%lld, %s, %s)", parameter_number,
                             parameter_index.ToString(),
                             kind == kMustAlias ? "must-alias" : "may-alias");
    }
    */



/*

class A {
  using AliasFn = B::FunctionRef<void(int a)>;
  //    indentifier = defining_type_id
  //                  defining-type-specifier-seq abstract-declarator?
  //                  defining-type-specifier
  //                  type-specifier
  //                  simple-type-specifier
  //                  nested-name-specifier? type-name
  //
  //                  FunctionRef<void(int a)>
  //                  type-name
  //                  typedef-name
  //                  simple-template-id
  //                  template-name < template-argument >
  //
  //                  void(int a)
  //                  template-argument
  //                  type-id
  //                  type-specifier-seq abstract-declarator?
  //                  type-specifier abstract-declarator
  
};
/*
class RemoteProfilerSessionManager {
  explicit RemoteProfilerSessionManager(    tensorflow::RemoteProfilerSessionManagerOptions options,      tensorflow::ProfileRequest request, AddressResolver resolver);
  std::unique_ptr<tensorflow::ProfileResponse> WaitForCompletion(absl::Status& out_status);
absl::string_view GetServiceAddress() const { return service_address_; }
};
*/
//float GetEnvVar(int i, size_t (*convert)(int*a)) {}
/*

float GetEnvVar(int i, size_t (*convert)(int*a)) {}

class A {

  A(int a) {}

};

inline int64_t available_tokens() TF_LOCKS_EXCLUDED(mu_) {
    mutex_lock l(mu_);
    UpdateState();
    return available_tokens_;
  }

virtual CURLcode curl_easy_setopt(
                                  //CURL* curl,
                                  //CURLoption option,
                                  size_t (*param)(void*, size_t, size_t, FILE*)
                                  ) = 0;
*/

//using LAliasFn = BC<C(A, float)>;


//int a = const_cast<const HloInstruction*>(this);
//int HloInstruction(const HloInstruction&) = delete;


//using AliasFn = A<void(const ShapeIndex& output_index, const Alias&)>;
//int HloInputOutputAliasConfig()  {}


  // Returns the backend-specific configuration for how a backend should compile
  // this HLO. The meaning of the field is backend specific. Not for use before
  // or during general HLO optimization, since HLO optimizations do not preserve
  // this field and they cannot interpret it due to its meaning being backend
  // specific. Except for CustomCall, where this field is preserved and no
  // general HLO optimization needs to interpret it.
  //
  // ConfigProto should be a protobuf Message type.


/*

class HloModule;

class HloInputOutputAliasConfig {
 public:
  // The kind of aliases which can be set. A kMayAlias is one setup at
  // compilation time by the user, and has to be respected. A kMustAlias one
  // might be setup by the compiler, if it decides it is convenient to do so.

  enum AliasKind {
    kMayAlias,
    kMustAlias,
  };



  // Defines the alias information for a given output buffer. A given output
  // buffer shape index can refer only to one parameter+index.
  struct Alias {
    Alias(int64_t parameter_number, ShapeIndex parameter_index,
          AliasKind kind = kMayAlias)
        : parameter_number(parameter_number),
          parameter_index(std::move(parameter_index)),
          kind(kind) {}

    int64_t parameter_number;
    ShapeIndex parameter_index;
    AliasKind kind;

    bool must_alias() const { return kind == kMustAlias; }

    std::string ToString() const {
      return absl::StrFormat("(%lld, %s, %s)", parameter_number,
                             parameter_index.ToString(),
                             kind == kMustAlias ? "must-alias" : "may-alias");
    }
  };



  //HloInputOutputAliasConfig() = default;

  explicit HloInputOutputAliasConfig(Shape output_shape)
      : alias_(std::move(output_shape)) {}

  // Sets up alias config from `output_index` to `param_index` at
  // `param_number`.
  absl::Status SetUpAlias(const ShapeIndex& output_index, int64_t param_number,
                          const ShapeIndex& param_index,
                          AliasKind must_alias = kMayAlias);

  // Returns true if the given parameter is aliased with one of the output
  // buffers.
  bool ParameterHasAlias(int64_t param_number,
                         const ShapeIndex& param_index) const {
    return GetAliasedOutput(param_number, param_index).has_value();
  }

 bool OutputHasAlias(const ShapeIndex& output_index) const;

  // (De)Serializes an HloInputOutputAliasConfig to/from an
  // HloInputOutputAliasProto.
  HloInputOutputAliasProto ToProto() const;

  static absl::StatusOr<HloInputOutputAliasConfig> CreateFromProto(
      Shape output_shape, const HloInputOutputAliasProto& proto);

  // Returns the output index that the given parameter and parameter index is
  // aliased with. A nullopt is returned if there is no output that is aliased
  // with the parameter number and index.
  std::optional<ShapeIndex> GetAliasedOutput(
      int64_t param_number, const ShapeIndex& param_index) const;

  // Returns the number of parameter and index of the parameter buffer that the
  // given output buffer index is aliased with. A nullopt is returned if there
  // is no parameter is aliased with the specific output.
  std::optional<Alias> GetAliasedParameter(
      const ShapeIndex& output_index) const;

  // Returns if the parameter at the given parameter number and parameter
  // index must-alias with an output.
  bool ParameterMustAlias(int64_t param_number,
                          const ShapeIndex& param_index) const;

  using AliasFn =
      absl::FunctionRef<void(const ShapeIndex& output_index, const Alias&)>;

  // Iterates through each aliased output and input.
  void ForEachAlias(AliasFn fn) const;

  using AliasFnWithStatus = absl::FunctionRef<absl::Status(
      const ShapeIndex& output_index, const Alias&)>;

  // Verifies that the given config is valid for the given module.
  // Specifically, the config's input and output should be in-bound and size ofF
  // the aliased buffers should match.
  absl::Status Verify(const HloModule& module,
                      absl::FunctionRef<int64_t(const Shape&)> size_func) const;

  absl::Status ForEachAliasWithStatus(AliasFnWithStatus fn) const;

  // Returns the shape of the output of the alias config.
  const Shape& shape() const;

  std::string ToString() const;

  std::string ToShortString() const;
private:
  // A ShapeTree which indicates the list of buffers that's expected to be
  // aliased. The key on this shape tree represents the output index. The value
  // is an Alias data structure which defines the input parameter coordinates.
  // If the value is nullopt, it means there is no parameter aliasing for this
  // output.
  ShapeTree<std::optional<Alias>> alias_;

  
};

//static absl::StatusOr<HloInputOutputAliasConfig> CreateFromProto(int output_shape);
//static A<T> CreateFromProto(int a);



//using OriginalValue = ShapeTree<std::optional<OriginalArray>>;
//using OriginalValue = ShapeTree<A>;


/*
explicit BackendConfigWrapper(std::string raw_string)
      : raw_string_(std::move(raw_string)) {}



template <typename T, size_t kBlockSize = 1<<16    >
class BlockedQueue final
  : public QueueBaseInternal::BlockedQueueBase<T, kBlockSize, false> { int a;};


uint64_t kFlowMask = 1+(2<<3); // = (1ULL << 56) - 1;


  enum class [[deprecated("Use PrimitiveType and Order")]] Type : uint8_t{
      kFloat,
      kFloatTotalOrder,
      kSigned,
      kUnsigned,
  };



struct DenseInlinedRep {
      alignas(kMinimumAlignment) char data[kMaxInlinedBytes];
    };


template <typename ReturnT, typename ElementwiseT = ReturnT>
class HloEvaluatorTypedVisitor : public ConstDfsHloVisitorWithDefault {
 private:
  ABSL_ATTRIBUTE_NOINLINE absl::Status UnsupportedTypeError(
      const HloInstruction* instruction) {
    return InvalidArgument(
        "Unsupported type for %s: %s", HloOpcodeString(instruction->opcode()),
        PrimitiveType_Name(instruction->shape().element_type()));
  }
};



template <class T>
inline PtrVec<T>::operator std::vector<T>() const {
  if (empty()) return {};
  return std::vector<T>(begin(), end());
}



template <class T>
inline T const* PtrVec<T>::data() const {}

namespace foo {
  template <class T>
  class Sar {
    //Sar() {}
  };
  
template <class T> Sar<T>::Sar() {}

Sar::Sar() {}


  
}
  

namespace mylib {

  namespace foo {

    
    //  This is class Foo documentation.


    class Foo {
    public:
      enum class FooKind {
        k1,
        k2,
      };
      char Main[] = "main";

      // This is a Foo constructor documentation.
      Foo(int default_value=0, std::shared_ptr<Foo> other_=nullptr): value(default_value), flag(false), other(other_.get()) { }

      // This is a Foo destructor documentation.
      ~Foo();
      
      // This is a Foo method add documentation.
      int add(int y) {
        int i;
        return value + y;
      }
      // This is a Foo method mul documentation.
      int mul(int y);

      // This is a Foo attribute value documentation.
      int value;
      bool flag;
      Foo* other;

      // This is a struct Bar documentation.
      struct Bar {
        int a;
        // This is a Bar attribure b documentation.
        int b;
        ~Bar() {
          a = 0;
        }
      };

      char Main[] = "main";

      
    };



    
    int Foo::mul(int y) {
      return value * y;
    }

    // This is get_value function documentation.
    int get_value(const Foo& f) {
      return f.value;
    }

    bool is_valid(Foo* f) {
      return f != nullptr;
    }

    template <>
    int foo_variable;
  }
  int mylib_variable;
}

namespace mylib2 {

class A {

template <int* = nullptr>
  bool foo() const {
      return false;
  }
  
};
  
  // This is class Bar documentation
  class Car: public Foo {
  public:
    int mul(int y, std::string opaque="", int b) {
      return value + y;
    }
  };

  Car::Car() {}

}





/*
 */
