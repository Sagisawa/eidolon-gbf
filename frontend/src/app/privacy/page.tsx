import { List, ListItem } from "@astryxdesign/core/List";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";

import { LegalFooter } from "@/components/LegalFooter";
import { PageShell } from "@/components/PageShell";
import { SectionHeading, SubpageHeader } from "@/components/SubpageHeader";
import { copy } from "@/i18n";

const t = copy.privacy;

export const metadata = { title: copy.legal.pageTitle(t.title) };

export default function PrivacyPage() {
  return (
    <PageShell
      contentWidth={640}
      padding={4}
      header={<SubpageHeader title={t.title} backHref="/login" />}
      footer={<LegalFooter />}
    >
      <VStack gap={8} paddingBlock={6}>
        {t.sections.map((section) => (
          <VStack as="section" key={section.title} gap={3}>
            <SectionHeading>{section.title}</SectionHeading>
            {section.items.length > 0 && (
              <List hasDividers>
                {section.items.map((item) => (
                  <ListItem key={item.term} label={<Text weight="semibold">{item.term}</Text>} description={<Text>{item.text}</Text>} />
                ))}
              </List>
            )}
            {section.notes.map((note) => (
              <Text as="p" key={note}>
                {note}
              </Text>
            ))}
          </VStack>
        ))}
      </VStack>
    </PageShell>
  );
}
