package local.alba;

import android.content.Context;
import android.graphics.Typeface;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.style.StyleSpan;
import android.text.style.TypefaceSpan;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TableLayout;
import android.widget.TableRow;
import android.widget.TextView;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Native selectable markdown: fenced code, emphasis, headings and tables. */
final class NativeMarkdown {
    static TextView text(Context context,String content){
        TextView view=new TextView(context);view.setTextColor(new NativeUi(context).ink);view.setTextSize(16);view.setLineSpacing(NativeUi.dp(context,3),1.15f);view.setIncludeFontPadding(false);view.setTextIsSelectable(true);view.setPadding(0,NativeUi.dp(context,4),0,NativeUi.dp(context,4));
        SpannableStringBuilder result=new SpannableStringBuilder();
        Matcher matcher=Pattern.compile("(\\*\\*(.+?)\\*\\*|`([^`]+)`)").matcher(content);int end=0;
        while(matcher.find()){
            result.append(content.substring(end,matcher.start()));int start=result.length();
            result.append(matcher.group(2)!=null?matcher.group(2):matcher.group(3));
            result.setSpan(matcher.group(2)!=null?new StyleSpan(Typeface.BOLD):new TypefaceSpan("monospace"),start,result.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);end=matcher.end();
        }
        result.append(content.substring(end));view.setText(result);return view;
    }
    static void render(Context context,LinearLayout target,String markdown){
        String[] sections=markdown.split("```",-1);
        for(int i=0;i<sections.length;i++){
            String section=sections[i];if(section.isEmpty())continue;
            if(i%2==1){int newline=section.indexOf('\n');String code=newline>=0?section.substring(newline+1):section;
                HorizontalScrollView scroll=new HorizontalScrollView(context);TextView view=text(context,code);view.setTypeface(Typeface.MONOSPACE);view.setTextSize(13);view.setPadding(NativeUi.dp(context,14),NativeUi.dp(context,12),NativeUi.dp(context,14),NativeUi.dp(context,12));scroll.setBackground(NativeUi.shape(context,new NativeUi(context).soft,14,0));scroll.addView(view);target.addView(scroll);continue;}
            String[] lines=section.split("\n");StringBuilder prose=new StringBuilder();
            for(int line=0;line<lines.length;line++){
                if(lines[line].trim().startsWith("|")&&line+1<lines.length&&lines[line+1].matches(".*\\|[ :|-]+\\|.*")){
                    if(prose.length()>0){target.addView(text(context,prose.toString()));prose.setLength(0);}
                    TableLayout table=new TableLayout(context);int row=0;
                    while(line<lines.length&&lines[line].trim().startsWith("|")){
                        if(row!=1){TableRow tr=new TableRow(context);for(String cell:lines[line].split("\\|")){if(cell.trim().isEmpty())continue;TextView value=text(context,cell.trim());value.setPadding(16,8,16,8);if(row==0)value.setTypeface(null,Typeface.BOLD);tr.addView(value);}table.addView(tr);}row++;line++;
                    }
                    line--;HorizontalScrollView scroll=new HorizontalScrollView(context);scroll.addView(table);target.addView(scroll);
                }else prose.append(lines[line].replaceFirst("^#{1,6} +","")).append('\n');
            }
            if(prose.length()>0)target.addView(text(context,prose.toString().trim()));
        }
    }
}
