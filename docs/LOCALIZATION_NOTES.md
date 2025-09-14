# Localization Notes

## Documentation Language Strategy

This project maintains documentation in multiple languages to serve our international user base:

### English Documentation (Primary)
- **Main README**: `/README.md` - Primary project documentation in English
- **Technical Docs**: All files in `/docs/` except localization files
- **Code Comments**: All source code comments and docstrings in English

### Localized Documentation
- **README_ZN.md**: Chinese (中文) version of the main README
  - Intentionally kept in Chinese for Chinese-speaking users
  - Provides complete project documentation in simplified Chinese
  - Maintained as a separate file to serve the significant Chinese user base

### Translation Status
- ✅ **Core Source Code**: All Chinese comments and strings translated to English
- ✅ **README_MULTI.md**: Translated from Chinese to English (multi-currency bot documentation)
- ✅ **Technical Documentation**: All technical docs in English
- 🌐 **README_ZN.md**: Intentionally kept in Chinese as a localization file

## Why Keep README_ZN.md in Chinese?

1. **User Accessibility**: Large portion of crypto traders are Chinese-speaking
2. **Localization Best Practice**: Separate language versions allow users to choose their preferred language
3. **SEO and Discovery**: Chinese documentation helps Chinese users find and understand the project
4. **Community Support**: Enables Chinese community to contribute and provide support in their native language

## File Naming Convention

- Default files (no suffix): English
- `_ZN` suffix: Chinese (Zhōngwén/中文)
- `_MULTI` suffix: Multi-currency specific documentation (now in English)

## Future Localization

If adding more languages, follow this pattern:
- `README_JA.md` for Japanese
- `README_KO.md` for Korean
- `README_ES.md` for Spanish
- etc.

---

**Note**: The main codebase and all technical documentation are maintained in English to ensure international accessibility and collaboration.